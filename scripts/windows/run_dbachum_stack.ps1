param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8080,

    [ValidateRange(1, 60)]
    [int]$KeepLogs = 5,

    [ValidateRange(1, 1024)]
    [int]$MaxLogSizeMB = 10
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$ServerScript = Join-Path $ProjectRoot 'scripts\windows\run_dbachum.ps1'
$CollectorScript = Join-Path $ProjectRoot 'scripts\windows\run_collector.ps1'
$EnvFile = Join-Path $ProjectRoot 'backend\.env'
$LogDir = Join-Path $ProjectRoot 'logs'
$LogFile = Join-Path $LogDir 'dbachum-stack.log'
$PowerShellExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'

if (-not (Test-Path $ServerScript)) {
    throw "DBAChum server launcher was not found: $ServerScript"
}

if (-not (Test-Path $CollectorScript)) {
    throw "DBAChum collector launcher was not found: $CollectorScript"
}

if (-not (Test-Path $PowerShellExe)) {
    throw "Windows PowerShell was not found: $PowerShellExe"
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

if (Test-Path $LogFile) {
    $maxBytes = $MaxLogSizeMB * 1MB
    if ((Get-Item $LogFile).Length -ge $maxBytes) {
        $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        Move-Item $LogFile (Join-Path $LogDir "dbachum-stack-$stamp.log")
    }
}

Get-ChildItem $LogDir -Filter 'dbachum-stack-*.log' -File |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip $KeepLogs |
    Remove-Item -Force

$CollectorEnabled = $true
if (Test-Path $EnvFile) {
    $collectorSetting = Get-Content $EnvFile |
        Where-Object { $_ -match '^\s*METRICS_COLLECTOR_ENABLED\s*=' } |
        Select-Object -First 1

    if ($null -ne $collectorSetting) {
        $collectorValue = (($collectorSetting -split '=', 2)[1]).Trim().Trim([char]34).Trim([char]39).ToLowerInvariant()
        if ($collectorValue -in @('false', '0', 'no', 'off')) {
            $CollectorEnabled = $false
        }
    }
}

function Write-StackLog([string]$Message) {
    "[$(Get-Date -Format o)] $Message" | Out-File -FilePath $LogFile -Append -Encoding utf8
}

# A Windows Job Object gives the Scheduled Task one real lifecycle boundary.
# JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE guarantees that when Task Scheduler stops
# this supervisor, both child launchers and their Python descendants are killed.
if (-not ('DBAChum.WindowsJob' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

namespace DBAChum
{
    public static class WindowsJob
    {
        private const uint JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000;
        private const int JobObjectExtendedLimitInformation = 9;

        [StructLayout(LayoutKind.Sequential)]
        private struct JOBOBJECT_BASIC_LIMIT_INFORMATION
        {
            public long PerProcessUserTimeLimit;
            public long PerJobUserTimeLimit;
            public uint LimitFlags;
            public UIntPtr MinimumWorkingSetSize;
            public UIntPtr MaximumWorkingSetSize;
            public uint ActiveProcessLimit;
            public UIntPtr Affinity;
            public uint PriorityClass;
            public uint SchedulingClass;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct IO_COUNTERS
        {
            public ulong ReadOperationCount;
            public ulong WriteOperationCount;
            public ulong OtherOperationCount;
            public ulong ReadTransferCount;
            public ulong WriteTransferCount;
            public ulong OtherTransferCount;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct JOBOBJECT_EXTENDED_LIMIT_INFORMATION
        {
            public JOBOBJECT_BASIC_LIMIT_INFORMATION BasicLimitInformation;
            public IO_COUNTERS IoInfo;
            public UIntPtr ProcessMemoryLimit;
            public UIntPtr JobMemoryLimit;
            public UIntPtr PeakProcessMemoryUsed;
            public UIntPtr PeakJobMemoryUsed;
        }

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
        private static extern IntPtr CreateJobObject(IntPtr lpJobAttributes, string lpName);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool SetInformationJobObject(
            IntPtr hJob,
            int infoType,
            ref JOBOBJECT_EXTENDED_LIMIT_INFORMATION lpJobObjectInfo,
            uint cbJobObjectInfoLength
        );

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool CloseHandle(IntPtr handle);

        public static IntPtr CreateKillOnCloseJob()
        {
            IntPtr job = CreateJobObject(IntPtr.Zero, null);
            if (job == IntPtr.Zero)
            {
                throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
            }

            JOBOBJECT_EXTENDED_LIMIT_INFORMATION info = new JOBOBJECT_EXTENDED_LIMIT_INFORMATION();
            info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;

            uint length = (uint)Marshal.SizeOf(typeof(JOBOBJECT_EXTENDED_LIMIT_INFORMATION));
            if (!SetInformationJobObject(job, JobObjectExtendedLimitInformation, ref info, length))
            {
                int error = Marshal.GetLastWin32Error();
                CloseHandle(job);
                throw new System.ComponentModel.Win32Exception(error);
            }

            return job;
        }

        public static void Assign(IntPtr job, IntPtr process)
        {
            if (!AssignProcessToJobObject(job, process))
            {
                throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
            }
        }

        public static void Close(IntPtr handle)
        {
            if (handle != IntPtr.Zero)
            {
                CloseHandle(handle);
            }
        }
    }
}
'@
}

$jobHandle = [IntPtr]::Zero
$serverProcess = $null
$collectorProcess = $null

try {
    $jobHandle = [DBAChum.WindowsJob]::CreateKillOnCloseJob()

    $serverArgs = @(
        '-NoProfile'
        '-ExecutionPolicy'
        'Bypass'
        '-File'
        "`"$ServerScript`""
        '-Port'
        $Port.ToString()
        '-KeepLogs'
        $KeepLogs.ToString()
        '-MaxLogSizeMB'
        $MaxLogSizeMB.ToString()
    )

    $collectorArgs = @(
        '-NoProfile'
        '-ExecutionPolicy'
        'Bypass'
        '-File'
        "`"$CollectorScript`""
        '-KeepLogs'
        $KeepLogs.ToString()
        '-MaxLogSizeMB'
        $MaxLogSizeMB.ToString()
    )

    Write-StackLog "Starting DBAChum stack on port $Port."

    $serverProcess = Start-Process `
        -FilePath $PowerShellExe `
        -ArgumentList $serverArgs `
        -WorkingDirectory $ProjectRoot `
        -WindowStyle Hidden `
        -PassThru
    [DBAChum.WindowsJob]::Assign($jobHandle, $serverProcess.Handle)

    if ($CollectorEnabled) {
        $collectorProcess = Start-Process `
            -FilePath $PowerShellExe `
            -ArgumentList $collectorArgs `
            -WorkingDirectory $ProjectRoot `
            -WindowStyle Hidden `
            -PassThru
        [DBAChum.WindowsJob]::Assign($jobHandle, $collectorProcess.Handle)

        Write-StackLog "Started web launcher PID $($serverProcess.Id) and collector launcher PID $($collectorProcess.Id)."
    }
    else {
        Write-StackLog "Started web launcher PID $($serverProcess.Id). Collector is disabled by METRICS_COLLECTOR_ENABLED."
    }

    while ($true) {
        Start-Sleep -Seconds 1
        $serverProcess.Refresh()
        if ($null -ne $collectorProcess) {
            $collectorProcess.Refresh()
        }

        $serverExited = $serverProcess.HasExited
        $collectorExited = $null -ne $collectorProcess -and $collectorProcess.HasExited

        if ($serverExited -or $collectorExited) {
            $serverState = if ($serverExited) { "exited ($($serverProcess.ExitCode))" } else { 'running' }
            $collectorState = if ($null -eq $collectorProcess) { 'disabled' } elseif ($collectorExited) { "exited ($($collectorProcess.ExitCode))" } else { 'running' }

            Write-StackLog "Stack child stopped unexpectedly. Web: $serverState; Collector: $collectorState. Stopping the full stack so Task Scheduler can restart both."
            throw "DBAChum stack child exited. Web: $serverState; Collector: $collectorState."
        }
    }
}
finally {
    foreach ($process in @($serverProcess, $collectorProcess)) {
        if ($null -ne $process) {
            try {
                $process.Refresh()
                if (-not $process.HasExited) {
                    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
                }
            }
            catch {
                # The Job Object cleanup below is the final safety net.
            }
        }
    }

    if ($jobHandle -ne [IntPtr]::Zero) {
        [DBAChum.WindowsJob]::Close($jobHandle)
    }

    Write-StackLog 'DBAChum stack stopped.'
}
