# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Cloud Provider Integration (Issue #61)

Implements integrations for AWS, Azure, and GCP using REST APIs via aiohttp.
Provides read-only operations for listing resources and getting account info.
"""

import hashlib
import hmac
import logging
from datetime import datetime
from typing import Any, Dict, List
from urllib.parse import quote

import aiohttp
from integrations.base import (
    BaseIntegration,
    IntegrationAction,
    IntegrationConfig,
    IntegrationHealth,
    IntegrationStatus,
)

logger = logging.getLogger(__name__)


class AWSIntegration(BaseIntegration):
    """AWS integration using REST APIs with Signature Version 4."""

    def __init__(self, config: IntegrationConfig):
        super().__init__(config)
        self.region = config.extra.get("region", "us-east-1")
        self.access_key = config.api_key
        self.secret_key = config.api_secret

    async def test_connection(self) -> IntegrationHealth:
        """Test AWS connection by calling STS GetCallerIdentity."""
        start_time = datetime.utcnow()
        if not self.access_key or not self.secret_key:
            return IntegrationHealth(
                provider="aws",
                status=IntegrationStatus.ERROR,
                message="Missing AWS credentials",
            )

        try:
            result = await self._call_sts_action("GetCallerIdentity")
            latency = (datetime.utcnow() - start_time).total_seconds() * 1000

            if result.get("status_code") == 200:
                identity = (
                    result.get("body", {})
                    .get("GetCallerIdentityResponse", {})
                    .get("GetCallerIdentityResult", {})
                )
                self._status = IntegrationStatus.CONNECTED
                return IntegrationHealth(
                    provider="aws",
                    status=IntegrationStatus.CONNECTED,
                    latency_ms=latency,
                    message="Connected successfully",
                    details={"account": identity.get("Account", "unknown")},
                )
            return IntegrationHealth(
                provider="aws",
                status=IntegrationStatus.ERROR,
                message="Connection failed",
            )
        except Exception as exc:
            self.logger.error("AWS test_connection failed: %s", exc)
            return IntegrationHealth(
                provider="aws",
                status=IntegrationStatus.ERROR,
                message=str(exc),
            )

    def get_available_actions(self) -> List[IntegrationAction]:
        """Return list of available AWS actions."""
        return [
            IntegrationAction(
                name="list_ec2_instances",
                description="List EC2 instances",
                method="GET",
            ),
            IntegrationAction(
                name="list_s3_buckets",
                description="List S3 buckets",
                method="GET",
            ),
            IntegrationAction(
                name="get_account_info",
                description="Get AWS account information",
                method="GET",
            ),
        ]

    async def execute_action(
        self, action: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute an AWS action."""
        action_map = {
            "list_ec2_instances": self._list_ec2_instances,
            "list_s3_buckets": self._list_s3_buckets,
            "get_account_info": self._get_account_info,
        }

        handler = action_map.get(action)
        if not handler:
            raise ValueError(f"Unknown action: {action}")

        return await handler(params)

    async def _list_ec2_instances(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List EC2 instances in the configured region."""
        result = await self._call_ec2_action("DescribeInstances")
        if result.get("status_code") != 200:
            return {"instances": [], "error": result.get("error")}

        reservations = (
            result.get("body", {})
            .get("DescribeInstancesResponse", {})
            .get("reservationSet", {})
            .get("item", [])
        )

        instances = []
        for reservation in reservations:
            for instance in reservation.get("instancesSet", {}).get("item", []):
                instances.append(self._extract_instance_data(instance))

        return {"instances": instances, "region": self.region}

    async def _list_s3_buckets(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List S3 buckets."""
        result = await self._call_s3_action("GET", "/")
        if result.get("status_code") != 200:
            return {"buckets": [], "error": result.get("error")}

        buckets_xml = result.get("body", {}).get("ListAllMyBucketsResult", {})
        bucket_items = buckets_xml.get("Buckets", {}).get("Bucket", [])

        buckets = [
            {"name": b.get("Name"), "created": b.get("CreationDate")}
            for b in bucket_items
        ]
        return {"buckets": buckets}

    async def _get_account_info(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get AWS account information."""
        result = await self._call_sts_action("GetCallerIdentity")
        if result.get("status_code") != 200:
            return {"error": result.get("error")}

        identity = (
            result.get("body", {})
            .get("GetCallerIdentityResponse", {})
            .get("GetCallerIdentityResult", {})
        )

        return {
            "account_id": identity.get("Account"),
            "user_id": identity.get("UserId"),
            "arn": identity.get("Arn"),
        }

    async def _call_ec2_action(self, action: str) -> Dict[str, Any]:
        """Call EC2 API action with SigV4 signing."""
        host = f"ec2.{self.region}.amazonaws.com"
        url = f"https://{host}/"
        params_str = f"Action={action}&Version=2016-11-15"

        headers = self._sign_request("GET", host, "/", params_str, "ec2")
        full_url = f"{url}?{params_str}"

        return await self._make_aws_request("GET", full_url, headers)

    async def _call_s3_action(self, method: str, path: str) -> Dict[str, Any]:
        """Call S3 API action with SigV4 signing."""
        host = "s3.amazonaws.com"
        url = f"https://{host}{path}"
        headers = self._sign_request(method, host, path, "", "s3")
        return await self._make_aws_request(method, url, headers)

    async def _call_sts_action(self, action: str) -> Dict[str, Any]:
        """Call STS API action with SigV4 signing."""
        host = "sts.amazonaws.com"
        url = f"https://{host}/"
        params_str = f"Action={action}&Version=2011-06-15"
        headers = self._sign_request("GET", host, "/", params_str, "sts")
        full_url = f"{url}?{params_str}"
        return await self._make_aws_request("GET", full_url, headers)

    def _sign_request(
        self,
        method: str,
        host: str,
        path: str,
        query: str,
        service: str,
    ) -> Dict[str, str]:
        """Create AWS Signature Version 4 headers."""
        now = datetime.utcnow()
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")

        canonical_uri = quote(path, safe="/")
        canonical_headers = f"host:{host}\nx-amz-date:{amz_date}\n"
        signed_headers = "host;x-amz-date"
        payload_hash = hashlib.sha256(b"").hexdigest()

        canonical_request = (
            f"{method}\n{canonical_uri}\n{query}\n"
            f"{canonical_headers}\n{signed_headers}\n{payload_hash}"
        )

        credential_scope = f"{date_stamp}/{self.region}/{service}/aws4_request"
        string_to_sign = (
            f"AWS4-HMAC-SHA256\n{amz_date}\n{credential_scope}\n"
            f"{hashlib.sha256(canonical_request.encode()).hexdigest()}"
        )

        signing_key = self._get_signature_key(
            self.secret_key, date_stamp, self.region, service
        )
        signature = hmac.new(
            signing_key, string_to_sign.encode(), hashlib.sha256
        ).hexdigest()

        authorization = (
            f"AWS4-HMAC-SHA256 Credential={self.access_key}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )

        return {
            "Authorization": authorization,
            "x-amz-date": amz_date,
            "Host": host,
        }

    def _get_signature_key(
        self, key: str, date_stamp: str, region: str, service: str
    ) -> bytes:
        """Derive AWS signing key."""
        k_date = hmac.new(
            f"AWS4{key}".encode(), date_stamp.encode(), hashlib.sha256
        ).digest()
        k_region = hmac.new(k_date, region.encode(), hashlib.sha256).digest()
        k_service = hmac.new(k_region, service.encode(), hashlib.sha256).digest()
        k_signing = hmac.new(k_service, b"aws4_request", hashlib.sha256).digest()
        return k_signing

    async def _make_aws_request(
        self, method: str, url: str, headers: Dict[str, str]
    ) -> Dict[str, Any]:
        """Make HTTP request to AWS API."""
        try:
            timeout = aiohttp.ClientTimeout(total=30.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.request(method, url, headers=headers) as resp:
                    text = await resp.text()
                    body = self._parse_xml_response(text)
                    return {
                        "status_code": resp.status,
                        "body": body,
                        "headers": dict(resp.headers),
                    }
        except aiohttp.ClientError as exc:
            self.logger.warning("AWS request to %s failed: %s", url, exc)
            return {"status_code": 0, "body": {}, "error": str(exc)}

    def _parse_xml_response(self, xml_text: str) -> Dict[str, Any]:
        """Parse AWS XML response into dict."""
        try:
            import defusedxml.ElementTree as ET

            root = ET.fromstring(xml_text)
            return self._element_to_dict(root)
        except Exception as exc:
            self.logger.warning("Failed to parse XML: %s", exc)
            return {}

    def _element_to_dict(self, element) -> Dict[str, Any]:
        """Convert XML element to dict."""
        result = {}
        for child in element:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if len(child) == 0:
                result[tag] = child.text
            else:
                child_dict = self._element_to_dict(child)
                if tag in result:
                    if not isinstance(result[tag], list):
                        result[tag] = [result[tag]]
                    result[tag].append(child_dict)
                else:
                    result[tag] = child_dict
        return result

    def _extract_instance_data(self, instance: Dict[str, Any]) -> Dict[str, Any]:
        """Extract relevant EC2 instance data."""
        return {
            "instance_id": instance.get("instanceId"),
            "instance_type": instance.get("instanceType"),
            "state": instance.get("instanceState", {}).get("name"),
            "launch_time": instance.get("launchTime"),
            "availability_zone": instance.get("placement", {}).get("availabilityZone"),
        }


class AzureIntegration(BaseIntegration):
    """Azure integration using REST APIs with Bearer token auth."""

    def __init__(self, config: IntegrationConfig):
        super().__init__(config)
        self.subscription_id = config.extra.get("subscription_id")
        self.tenant_id = config.extra.get("tenant_id")
        self.access_token = config.token

    async def test_connection(self) -> IntegrationHealth:
        """Test Azure connection by getting subscription details."""
        start_time = datetime.utcnow()
        if not self.access_token or not self.subscription_id:
            return IntegrationHealth(
                provider="azure",
                status=IntegrationStatus.ERROR,
                message="Missing Azure credentials",
            )

        try:
            url = (
                f"https://management.azure.com/subscriptions/"
                f"{self.subscription_id}?api-version=2020-01-01"
            )
            result = await self._make_azure_request("GET", url)
            latency = (datetime.utcnow() - start_time).total_seconds() * 1000

            if result.get("status_code") == 200:
                sub_data = result.get("body", {})
                self._status = IntegrationStatus.CONNECTED
                return IntegrationHealth(
                    provider="azure",
                    status=IntegrationStatus.CONNECTED,
                    latency_ms=latency,
                    message="Connected successfully",
                    details={"subscription": sub_data.get("displayName", "unknown")},
                )
            return IntegrationHealth(
                provider="azure",
                status=IntegrationStatus.ERROR,
                message="Connection failed",
            )
        except Exception as exc:
            self.logger.error("Azure test_connection failed: %s", exc)
            return IntegrationHealth(
                provider="azure",
                status=IntegrationStatus.ERROR,
                message=str(exc),
            )

    def get_available_actions(self) -> List[IntegrationAction]:
        """Return list of available Azure actions."""
        return [
            IntegrationAction(
                name="list_vms",
                description="List virtual machines",
                method="GET",
            ),
            IntegrationAction(
                name="list_storage_accounts",
                description="List storage accounts",
                method="GET",
            ),
            IntegrationAction(
                name="get_subscription_info",
                description="Get subscription information",
                method="GET",
            ),
        ]

    async def execute_action(
        self, action: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute an Azure action."""
        action_map = {
            "list_vms": self._list_vms,
            "list_storage_accounts": self._list_storage_accounts,
            "get_subscription_info": self._get_subscription_info,
        }

        handler = action_map.get(action)
        if not handler:
            raise ValueError(f"Unknown action: {action}")

        return await handler(params)

    async def _list_vms(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List Azure virtual machines."""
        url = (
            f"https://management.azure.com/subscriptions/"
            f"{self.subscription_id}/providers/Microsoft.Compute/"
            f"virtualMachines?api-version=2021-03-01"
        )
        result = await self._make_azure_request("GET", url)

        if result.get("status_code") != 200:
            return {"vms": [], "error": result.get("error")}

        vms = result.get("body", {}).get("value", [])
        return {
            "vms": [self._extract_vm_data(vm) for vm in vms],
            "count": len(vms),
        }

    async def _list_storage_accounts(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List Azure storage accounts."""
        url = (
            f"https://management.azure.com/subscriptions/"
            f"{self.subscription_id}/providers/Microsoft.Storage/"
            f"storageAccounts?api-version=2021-04-01"
        )
        result = await self._make_azure_request("GET", url)

        if result.get("status_code") != 200:
            return {"storage_accounts": [], "error": result.get("error")}

        accounts = result.get("body", {}).get("value", [])
        return {
            "storage_accounts": [self._extract_storage_data(acc) for acc in accounts],
            "count": len(accounts),
        }

    async def _get_subscription_info(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get Azure subscription information."""
        url = (
            f"https://management.azure.com/subscriptions/"
            f"{self.subscription_id}?api-version=2020-01-01"
        )
        result = await self._make_azure_request("GET", url)

        if result.get("status_code") != 200:
            return {"error": result.get("error")}

        sub_data = result.get("body", {})
        return {
            "subscription_id": sub_data.get("subscriptionId"),
            "display_name": sub_data.get("displayName"),
            "state": sub_data.get("state"),
            "tenant_id": sub_data.get("tenantId"),
        }

    async def _make_azure_request(self, method: str, url: str) -> Dict[str, Any]:
        """Make HTTP request to Azure API."""
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

        try:
            timeout = aiohttp.ClientTimeout(total=30.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.request(method, url, headers=headers) as resp:
                    body = await resp.json()
                    return {
                        "status_code": resp.status,
                        "body": body,
                        "headers": dict(resp.headers),
                    }
        except aiohttp.ClientError as exc:
            self.logger.warning("Azure request to %s failed: %s", url, exc)
            return {"status_code": 0, "body": {}, "error": str(exc)}

    def _extract_vm_data(self, vm: Dict[str, Any]) -> Dict[str, Any]:
        """Extract relevant VM data."""
        props = vm.get("properties", {})
        return {
            "name": vm.get("name"),
            "id": vm.get("id"),
            "location": vm.get("location"),
            "vm_size": props.get("hardwareProfile", {}).get("vmSize"),
            "provisioning_state": props.get("provisioningState"),
        }

    def _extract_storage_data(self, account: Dict[str, Any]) -> Dict[str, Any]:
        """Extract relevant storage account data."""
        props = account.get("properties", {})
        return {
            "name": account.get("name"),
            "id": account.get("id"),
            "location": account.get("location"),
            "sku": account.get("sku", {}).get("name"),
            "kind": account.get("kind"),
            "provisioning_state": props.get("provisioningState"),
        }


class GCPIntegration(BaseIntegration):
    """GCP integration using REST APIs with Bearer token auth."""

    def __init__(self, config: IntegrationConfig):
        super().__init__(config)
        self.project_id = config.extra.get("project_id")
        self.access_token = config.token

    async def test_connection(self) -> IntegrationHealth:
        """Test GCP connection by getting project details."""
        start_time = datetime.utcnow()
        if not self.access_token or not self.project_id:
            return IntegrationHealth(
                provider="gcp",
                status=IntegrationStatus.ERROR,
                message="Missing GCP credentials",
            )

        try:
            url = (
                f"https://cloudresourcemanager.googleapis.com/v1/"
                f"projects/{self.project_id}"
            )
            result = await self._make_gcp_request("GET", url)
            latency = (datetime.utcnow() - start_time).total_seconds() * 1000

            if result.get("status_code") == 200:
                project = result.get("body", {})
                self._status = IntegrationStatus.CONNECTED
                return IntegrationHealth(
                    provider="gcp",
                    status=IntegrationStatus.CONNECTED,
                    latency_ms=latency,
                    message="Connected successfully",
                    details={"project": project.get("name", "unknown")},
                )
            return IntegrationHealth(
                provider="gcp",
                status=IntegrationStatus.ERROR,
                message="Connection failed",
            )
        except Exception as exc:
            self.logger.error("GCP test_connection failed: %s", exc)
            return IntegrationHealth(
                provider="gcp",
                status=IntegrationStatus.ERROR,
                message=str(exc),
            )

    def get_available_actions(self) -> List[IntegrationAction]:
        """Return list of available GCP actions."""
        return [
            IntegrationAction(
                name="list_instances",
                description="List compute instances",
                method="GET",
            ),
            IntegrationAction(
                name="list_storage_buckets",
                description="List storage buckets",
                method="GET",
            ),
            IntegrationAction(
                name="get_project_info",
                description="Get project information",
                method="GET",
            ),
        ]

    async def execute_action(
        self, action: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a GCP action."""
        action_map = {
            "list_instances": self._list_instances,
            "list_storage_buckets": self._list_storage_buckets,
            "get_project_info": self._get_project_info,
        }

        handler = action_map.get(action)
        if not handler:
            raise ValueError(f"Unknown action: {action}")

        return await handler(params)

    async def _list_instances(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List GCP compute instances."""
        zone = params.get("zone", "us-central1-a")
        url = (
            f"https://compute.googleapis.com/compute/v1/projects/"
            f"{self.project_id}/zones/{zone}/instances"
        )
        result = await self._make_gcp_request("GET", url)

        if result.get("status_code") != 200:
            return {"instances": [], "error": result.get("error")}

        instances = result.get("body", {}).get("items", [])
        return {
            "instances": [self._extract_instance_data(inst) for inst in instances],
            "zone": zone,
            "count": len(instances),
        }

    async def _list_storage_buckets(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List GCP storage buckets."""
        url = (
            f"https://storage.googleapis.com/storage/v1/b?" f"project={self.project_id}"
        )
        result = await self._make_gcp_request("GET", url)

        if result.get("status_code") != 200:
            return {"buckets": [], "error": result.get("error")}

        buckets = result.get("body", {}).get("items", [])
        return {
            "buckets": [self._extract_bucket_data(bucket) for bucket in buckets],
            "count": len(buckets),
        }

    async def _get_project_info(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get GCP project information."""
        url = (
            f"https://cloudresourcemanager.googleapis.com/v1/"
            f"projects/{self.project_id}"
        )
        result = await self._make_gcp_request("GET", url)

        if result.get("status_code") != 200:
            return {"error": result.get("error")}

        project = result.get("body", {})
        return {
            "project_id": project.get("projectId"),
            "name": project.get("name"),
            "project_number": project.get("projectNumber"),
            "lifecycle_state": project.get("lifecycleState"),
        }

    async def _make_gcp_request(self, method: str, url: str) -> Dict[str, Any]:
        """Make HTTP request to GCP API."""
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

        try:
            timeout = aiohttp.ClientTimeout(total=30.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.request(method, url, headers=headers) as resp:
                    body = await resp.json()
                    return {
                        "status_code": resp.status,
                        "body": body,
                        "headers": dict(resp.headers),
                    }
        except aiohttp.ClientError as exc:
            self.logger.warning("GCP request to %s failed: %s", url, exc)
            return {"status_code": 0, "body": {}, "error": str(exc)}

    def _extract_instance_data(self, instance: Dict[str, Any]) -> Dict[str, Any]:
        """Extract relevant instance data."""
        return {
            "name": instance.get("name"),
            "id": instance.get("id"),
            "machine_type": instance.get("machineType", "").split("/")[-1],
            "status": instance.get("status"),
            "zone": instance.get("zone", "").split("/")[-1],
            "creation_timestamp": instance.get("creationTimestamp"),
        }

    def _extract_bucket_data(self, bucket: Dict[str, Any]) -> Dict[str, Any]:
        """Extract relevant bucket data."""
        return {
            "name": bucket.get("name"),
            "id": bucket.get("id"),
            "location": bucket.get("location"),
            "storage_class": bucket.get("storageClass"),
            "time_created": bucket.get("timeCreated"),
        }
