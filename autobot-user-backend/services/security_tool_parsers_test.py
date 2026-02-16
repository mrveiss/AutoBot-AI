# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for Security Tool Output Parsers

Issue: #260
"""

from backend.services.security_tool_parsers import (
    GobusterParser,
    MasscanParser,
    NiktoParser,
    NmapParser,
    NucleiParser,
    SearchsploitParser,
    get_parser_registry,
)


class TestNmapParser:
    """Tests for NmapParser."""

    def test_can_parse_xml(self) -> None:
        """Test detection of nmap XML output."""
        parser = NmapParser()
        xml_output = '<?xml version="1.0"?><nmaprun></nmaprun>'
        assert parser.can_parse(xml_output)

    def test_can_parse_text(self) -> None:
        """Test detection of nmap text output."""
        parser = NmapParser()
        text_output = "Nmap scan report for 192.168.1.1"
        assert parser.can_parse(text_output)

    def test_can_parse_grepable(self) -> None:
        """Test detection of nmap grepable output."""
        parser = NmapParser()
        grep_output = "Host: 192.168.1.1 (web.local)"
        assert parser.can_parse(grep_output)

    def test_parse_xml_output(self) -> None:
        """Test parsing nmap XML output."""
        parser = NmapParser()
        xml_output = """<?xml version="1.0"?>
<nmaprun scanner="nmap" args="nmap -sV 192.168.1.1">
    <host>
        <status state="up"/>
        <address addr="192.168.1.1" addrtype="ipv4"/>
        <address addr="00:11:22:33:44:55" addrtype="mac" vendor="Test Vendor"/>
        <hostnames>
            <hostname name="web.local"/>
        </hostnames>
        <ports>
            <port protocol="tcp" portid="80">
                <state state="open"/>
                <service name="http" product="Apache" version="2.4.41"/>
            </port>
            <port protocol="tcp" portid="443">
                <state state="open"/>
                <service name="https" product="Apache" version="2.4.41"/>
            </port>
        </ports>
    </host>
    <runstats>
        <finished time="1234567890" timestr="Test Time" elapsed="10.5" exit="success"/>
        <hosts up="1" down="0" total="1"/>
    </runstats>
</nmaprun>"""

        result = parser.parse(xml_output)
        assert result.tool == "nmap"
        assert result.scan_type == "xml"
        assert len(result.hosts) == 1
        host = result.hosts[0]
        assert host.ip == "192.168.1.1"
        assert host.hostname == "web.local"
        assert host.status == "up"
        assert host.mac_address == "00:11:22:33:44:55"
        assert host.vendor == "Test Vendor"
        assert len(host.ports) == 2
        assert host.ports[0]["port"] == 80
        assert host.ports[0]["service"] == "http"
        assert host.ports[0]["product"] == "Apache"
        assert host.ports[0]["version"] == "2.4.41"

    def test_parse_text_output(self) -> None:
        """Test parsing nmap text output."""
        parser = NmapParser()
        text_output = """Starting Nmap 7.80
Nmap scan report for web.local (192.168.1.1)
Host is up (0.0010s latency).
PORT    STATE SERVICE  VERSION
22/tcp  open  ssh      OpenSSH 8.2p1
80/tcp  open  http     Apache httpd 2.4.41
443/tcp open  https    Apache httpd 2.4.41
MAC Address: 00:11:22:33:44:55 (Test Vendor)
OS details: Linux 5.4"""

        result = parser.parse(text_output)
        assert result.tool == "nmap"
        assert result.scan_type == "text"
        assert len(result.hosts) == 1
        host = result.hosts[0]
        assert host.ip == "192.168.1.1"
        assert host.hostname == "web.local"
        assert host.mac_address == "00:11:22:33:44:55"
        assert host.os_guess == "Linux 5.4"
        assert len(host.ports) == 3
        assert host.ports[0]["port"] == 22
        assert host.ports[0]["service"] == "ssh"

    def test_parse_empty_output(self) -> None:
        """Test parsing empty nmap output."""
        parser = NmapParser()
        result = parser.parse("")
        assert result.tool == "nmap"
        assert len(result.hosts) == 0


class TestMasscanParser:
    """Tests for MasscanParser."""

    def test_can_parse(self) -> None:
        """Test detection of masscan output."""
        parser = MasscanParser()
        assert parser.can_parse("Starting masscan")
        assert parser.can_parse("Discovered open port 80/tcp on 192.168.1.1")

    def test_parse_output(self) -> None:
        """Test parsing masscan output."""
        parser = MasscanParser()
        output = """Starting masscan 1.3.2
Discovered open port 80/tcp on 192.168.1.1
Discovered open port 443/tcp on 192.168.1.1
Discovered open port 22/tcp on 192.168.1.2
Discovered open port 3306/tcp on 192.168.1.3"""

        result = parser.parse(output)
        assert result.tool == "masscan"
        assert len(result.hosts) == 3

        host1 = next(h for h in result.hosts if h.ip == "192.168.1.1")
        assert len(host1.ports) == 2
        assert host1.ports[0]["port"] == 80
        assert host1.ports[1]["port"] == 443

    def test_parse_empty_output(self) -> None:
        """Test parsing empty masscan output."""
        parser = MasscanParser()
        result = parser.parse("Starting masscan\n")
        assert result.tool == "masscan"
        assert len(result.hosts) == 0


class TestNucleiParser:
    """Tests for NucleiParser."""

    def test_can_parse(self) -> None:
        """Test detection of nuclei output."""
        parser = NucleiParser()
        assert parser.can_parse("nuclei v2.5.0")
        assert parser.can_parse("[critical] [CVE-2021-1234] [http] example.com")

    def test_parse_output(self) -> None:
        """Test parsing nuclei output."""
        parser = NucleiParser()
        output = """[critical] [CVE-2021-1234] [http] https://192.168.1.1:8080/admin
[high] [CVE-2021-5678] [http] http://192.168.1.2/login
[medium] [exposed-panel] [http] https://web.local/phpmyadmin
[low] [info-disclosure] [http] http://192.168.1.1/.git/config"""

        result = parser.parse(output)
        assert result.tool == "nuclei"
        assert len(result.vulnerabilities) == 4

        crit_vuln = result.vulnerabilities[0]
        assert crit_vuln.host == "192.168.1.1"
        assert crit_vuln.port == 8080
        assert crit_vuln.severity == "critical"
        assert crit_vuln.title == "CVE-2021-1234"

        medium_vuln = result.vulnerabilities[2]
        assert medium_vuln.host == "web.local"
        assert medium_vuln.severity == "medium"

    def test_parse_empty_output(self) -> None:
        """Test parsing empty nuclei output."""
        parser = NucleiParser()
        result = parser.parse("")
        assert result.tool == "nuclei"
        assert len(result.vulnerabilities) == 0


class TestNiktoParser:
    """Tests for NiktoParser."""

    def test_can_parse(self) -> None:
        """Test detection of nikto output."""
        parser = NiktoParser()
        assert parser.can_parse("- Nikto v2.5.0")
        assert parser.can_parse("+ Target IP:          192.168.1.1")

    def test_parse_output(self) -> None:
        """Test parsing nikto output."""
        parser = NiktoParser()
        output = """- Nikto v2.5.0
---------------------------------------------------------------------------
+ Target IP:          192.168.1.1
+ Target Hostname:    web.local
+ Target Port:        80
+ Server: Apache/2.4.41 (Ubuntu)
+ The anti-clickjacking X-Frame-Options header is not present.
+ The X-Content-Type-Options header is not set.
+ /admin/: Directory indexing found.
+ OSVDB-3268: /admin/: Directory listing found
+ OSVDB-3233: /icons/README: Apache default file found
+ /backup.sql: Database backup file found (potential sensitive data)
+ 7535 requests: 0 error(s) and 6 item(s) reported"""

        result = parser.parse(output)
        assert result.tool == "nikto"
        assert len(result.hosts) == 1
        assert result.hosts[0].ip == "192.168.1.1"
        assert result.hosts[0].hostname == "web.local"

        assert len(result.vulnerabilities) == 6

        # Check severity classification
        osvdb_vuln = next(v for v in result.vulnerabilities if "OSVDB-3268" in v.title)
        assert osvdb_vuln.severity == "medium"
        assert osvdb_vuln.port == 80

        dir_vuln = next(
            v for v in result.vulnerabilities if "Directory indexing" in v.title
        )
        assert dir_vuln.severity == "low"

    def test_parse_empty_output(self) -> None:
        """Test parsing empty nikto output."""
        parser = NiktoParser()
        result = parser.parse("- Nikto v2.5.0\n")
        assert result.tool == "nikto"
        assert len(result.vulnerabilities) == 0


class TestGobusterParser:
    """Tests for GobusterParser."""

    def test_can_parse(self) -> None:
        """Test detection of gobuster output."""
        parser = GobusterParser()
        assert parser.can_parse("Gobuster v3.1.0")
        assert parser.can_parse("[+] Url:            http://192.168.1.1")

    def test_parse_output(self) -> None:
        """Test parsing gobuster output."""
        parser = GobusterParser()
        output = """===============================================================
Gobuster v3.1.0
by OJ Reeves (@TheColonial) & Christian Mehlmauer (@firefart)
===============================================================
[+] Url:            http://192.168.1.1
[+] Method:         GET
[+] Threads:        10
[+] Wordlist:       /usr/share/wordlists/dirb/common.txt
===============================================================
Starting gobuster
===============================================================
/admin                (Status: 200) [Size: 1234]
/login                (Status: 200) [Size: 5678]
/backup               (Status: 403) [Size: 277]
/.git                 (Status: 200) [Size: 0]
/.env                 (Status: 403) [Size: 277]
/images               (Status: 301) [Size: 0]
===============================================================
Finished
==============================================================="""

        result = parser.parse(output)
        assert result.tool == "gobuster"
        assert len(result.hosts) == 1
        assert result.hosts[0].ip == "192.168.1.1"

        assert len(result.vulnerabilities) == 6

        # Check severity classification
        git_vuln = next(v for v in result.vulnerabilities if ".git" in v.title)
        assert git_vuln.severity == "high"
        assert git_vuln.metadata["status_code"] == 200

        env_vuln = next(v for v in result.vulnerabilities if ".env" in v.title)
        assert env_vuln.severity == "medium"
        assert env_vuln.metadata["status_code"] == 403

        images_vuln = next(v for v in result.vulnerabilities if "images" in v.title)
        assert images_vuln.severity == "info"

    def test_parse_empty_output(self) -> None:
        """Test parsing empty gobuster output."""
        parser = GobusterParser()
        result = parser.parse("Gobuster v3.1.0\n")
        assert result.tool == "gobuster"
        assert len(result.vulnerabilities) == 0


class TestSearchsploitParser:
    """Tests for SearchsploitParser."""

    def test_can_parse(self) -> None:
        """Test detection of searchsploit output."""
        parser = SearchsploitParser()
        assert parser.can_parse("searchsploit Apache 2.4.41")
        assert parser.can_parse("Exploit Title                          |  Path")

    def test_parse_output(self) -> None:
        """Test parsing searchsploit output."""
        parser = SearchsploitParser()
        output = """searchsploit Apache 2.4.41
--------------------------------------- ---------------------------------
 Exploit Title                          |  Path
--------------------------------------- ---------------------------------
Apache 2.4.41 - Remote Code Execution   | exploits/linux/remote/48000.py
Apache 2.4.x - Buffer Overflow          | exploits/linux/remote/47999.c
Apache 2.4.x - Denial of Service        | exploits/linux/dos/47998.py
Apache Module - Information Disclosure  | exploits/linux/webapps/47997.txt
--------------------------------------- ---------------------------------
Shellcodes: No Results
Papers: No Results"""

        result = parser.parse(output)
        assert result.tool == "searchsploit"
        assert len(result.vulnerabilities) == 4

        # Check severity classification
        rce_vuln = result.vulnerabilities[0]
        assert "Remote Code Execution" in rce_vuln.title
        assert rce_vuln.severity == "critical"
        assert "48000.py" in rce_vuln.metadata["exploit_path"]

        overflow_vuln = result.vulnerabilities[1]
        assert "Buffer Overflow" in overflow_vuln.title
        assert overflow_vuln.severity == "high"

        dos_vuln = result.vulnerabilities[2]
        assert "Denial of Service" in dos_vuln.title
        assert dos_vuln.severity == "medium"

        info_vuln = result.vulnerabilities[3]
        assert "Information Disclosure" in info_vuln.title
        assert info_vuln.severity == "low"

    def test_parse_empty_output(self) -> None:
        """Test parsing empty searchsploit output."""
        parser = SearchsploitParser()
        result = parser.parse("searchsploit test\nShellcodes: No Results\n")
        assert result.tool == "searchsploit"
        assert len(result.vulnerabilities) == 0


class TestToolParserRegistry:
    """Tests for ToolParserRegistry."""

    def test_auto_detect_nmap(self) -> None:
        """Test auto-detection of nmap output."""
        registry = get_parser_registry()
        output = "Nmap scan report for 192.168.1.1"
        result = registry.detect_and_parse(output)
        assert result is not None
        assert result.tool == "nmap"

    def test_auto_detect_masscan(self) -> None:
        """Test auto-detection of masscan output."""
        registry = get_parser_registry()
        output = "Discovered open port 80/tcp on 192.168.1.1"
        result = registry.detect_and_parse(output)
        assert result is not None
        assert result.tool == "masscan"

    def test_auto_detect_nuclei(self) -> None:
        """Test auto-detection of nuclei output."""
        registry = get_parser_registry()
        output = "[critical] [CVE-2021-1234] [http] example.com"
        result = registry.detect_and_parse(output)
        assert result is not None
        assert result.tool == "nuclei"

    def test_auto_detect_nikto(self) -> None:
        """Test auto-detection of nikto output."""
        registry = get_parser_registry()
        output = "- Nikto v2.5.0\n+ Target IP:          192.168.1.1"
        result = registry.detect_and_parse(output)
        assert result is not None
        assert result.tool == "nikto"

    def test_auto_detect_gobuster(self) -> None:
        """Test auto-detection of gobuster output."""
        registry = get_parser_registry()
        output = "Gobuster v3.1.0\n[+] Url:            http://192.168.1.1"
        result = registry.detect_and_parse(output)
        assert result is not None
        assert result.tool == "gobuster"

    def test_auto_detect_searchsploit(self) -> None:
        """Test auto-detection of searchsploit output."""
        registry = get_parser_registry()
        output = "searchsploit Apache\nExploit Title                          |  Path"
        result = registry.detect_and_parse(output)
        assert result is not None
        assert result.tool == "searchsploit"

    def test_parse_with_tool(self) -> None:
        """Test parsing with specific tool name."""
        registry = get_parser_registry()
        output = "Nmap scan report for 192.168.1.1"
        result = registry.parse_with_tool(output, "nmap")
        assert result is not None
        assert result.tool == "nmap"

    def test_parse_with_unknown_tool(self) -> None:
        """Test parsing with unknown tool name."""
        registry = get_parser_registry()
        result = registry.parse_with_tool("some output", "unknown_tool")
        assert result is None

    def test_no_parser_matches(self) -> None:
        """Test when no parser matches."""
        registry = get_parser_registry()
        result = registry.detect_and_parse("random text with no tool signature")
        assert result is None
