# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# #19681: requirements.txt names the shared constraints by a path relative to the repo, which does not
# exist in an install directory, so pip aborted before installing anything. Keep a copy beside the
# installed requirements file and point its -c at that copy. pip resolves -c against the file holding it.

function Set-InstalledConstraints {
    param(
        [Parameter(Mandatory = $true)][string]$InstallPath,
        [string]$SourceDir = ""
    )

    $requirements = Join-Path $InstallPath "requirements.txt"
    $staged = Join-Path $InstallPath "constraints-shared.txt"

    if ($SourceDir) {
        $inRepo = Join-Path $SourceDir "..\..\..\constraints\shared.txt"
        $inPackage = Join-Path $SourceDir "constraints-shared.txt"
        foreach ($candidate in @($inRepo, $inPackage)) {
            if (Test-Path $candidate) {
                # An update run from the install directory finds the copy already in place.
                if ((Resolve-Path $candidate).Path -ne $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($staged)) {
                    Copy-Item -Path $candidate -Destination $staged -Force
                }
                break
            }
        }
    }

    if (-not (Test-Path $staged)) {
        throw "No shared constraints file for $requirements. Expected $staged."
    }

    $lines = Get-Content -Path $requirements -Encoding UTF8
    $rewritten = $lines -replace '^-c\s+\S+', '-c constraints-shared.txt'
    Set-Content -Path $requirements -Value $rewritten -Encoding UTF8
}
