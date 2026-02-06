# AutoBot NPU Worker - Health Check Script

param(
    [switch]$Detailed,
    [switch]$Benchmark,
    [int]$Port = 8082
)

$ErrorActionPreference = "SilentlyContinue"

function Write-Success { Write-Host $args -ForegroundColor Green }
function Write-Info { Write-Host $args -ForegroundColor Cyan }
function Write-Warning { Write-Host $args -ForegroundColor Yellow }
function Write-Error { Write-Host $args -ForegroundColor Red }

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AutoBot NPU Worker - Health Check" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check Windows Service
Write-Info "Checking Windows Service..."
$service = Get-Service -Name AutoBotNPUWorker -ErrorAction SilentlyContinue
if ($service) {
    if ($service.Status -eq "Running") {
        Write-Success "Service Status: Running"
    } else {
        Write-Error "Service Status: $($service.Status)"
    }
    Write-Host "  Startup Type: $($service.StartType)"
} else {
    Write-Error "Service not found (not installed)"
    exit 1
}

Write-Host ""

# Check HTTP endpoint
Write-Info "Checking HTTP endpoint..."
$healthUrl = "http://localhost:$Port/health"

try {
    $response = Invoke-RestMethod -Uri $healthUrl -Method Get -TimeoutSec 5
    Write-Success "HTTP Endpoint: Responding"

    Write-Host ""
    Write-Info "Worker Information:"
    Write-Host "  Worker ID: $($response.worker_id)"
    Write-Host "  Status: $($response.status)"
    Write-Host "  NPU Available: $($response.npu_available)"
    Write-Host "  Port: $Port"

    if ($response.loaded_models -and $response.loaded_models.Count -gt 0) {
        Write-Host "  Loaded Models: $($response.loaded_models -join ', ')"
    } else {
        Write-Host "  Loaded Models: None"
    }

    Write-Host ""
    Write-Info "Task Statistics:"
    Write-Host "  Tasks Completed: $($response.stats.tasks_completed)"
    Write-Host "  Tasks Failed: $($response.stats.tasks_failed)"
    Write-Host "  Avg Response Time: $([math]::Round($response.stats.average_response_time_ms, 2))ms"

    if ($response.npu_metrics) {
        Write-Host ""
        Write-Info "NPU Metrics:"
        Write-Host "  Utilization: $([math]::Round($response.npu_metrics.utilization_percent, 1))%"
        Write-Host "  Temperature: $([math]::Round($response.npu_metrics.temperature_c, 1))°C"
        Write-Host "  Power Usage: $([math]::Round($response.npu_metrics.power_usage_w, 2))W"
    }

    # Detailed statistics
    if ($Detailed) {
        Write-Host ""
        Write-Info "Fetching detailed statistics..."
        $statsUrl = "http://localhost:$Port/stats"
        try {
            $stats = Invoke-RestMethod -Uri $statsUrl -Method Get -TimeoutSec 5
            Write-Host ""
            Write-Info "Detailed Statistics:"
            Write-Host "  Uptime: $([math]::Round($stats.uptime_seconds / 60, 1)) minutes"

            if ($stats.cache_stats) {
                Write-Host "  Cache Size: $($stats.cache_stats.embedding_cache_size)"
                Write-Host "  Cache Hits: $($stats.cache_stats.cache_hits)"
                Write-Host "  Cache Hit Rate: $([math]::Round($stats.cache_stats.cache_hit_rate, 1))%"
            }

            if ($stats.loaded_models) {
                Write-Host ""
                Write-Info "Model Details:"
                foreach ($model in $stats.loaded_models.PSObject.Properties) {
                    Write-Host "  $($model.Name):"
                    Write-Host "    Size: $($model.Value.size_mb)MB"
                    Write-Host "    Device: $($model.Value.optimized_for_npu)"
                    Write-Host "    Last Used: $($model.Value.last_used)"
                }
            }
        } catch {
            Write-Warning "Could not fetch detailed statistics: $_"
        }
    }

    # Performance benchmark
    if ($Benchmark) {
        Write-Host ""
        Write-Info "Running performance benchmark..."
        $benchmarkUrl = "http://localhost:$Port/performance/benchmark"
        try {
            $benchmark = Invoke-RestMethod -Uri $benchmarkUrl -Method Get -TimeoutSec 60
            Write-Success "Benchmark completed"
            Write-Host ""
            Write-Info "Benchmark Results:"

            if ($benchmark.benchmarks.embedding_generation) {
                $embGen = $benchmark.benchmarks.embedding_generation
                Write-Host "  Embedding Generation:"
                Write-Host "    Texts Processed: $($embGen.texts_processed)"
                Write-Host "    Total Time: $([math]::Round($embGen.total_time_ms, 2))ms"
                Write-Host "    Avg per Text: $([math]::Round($embGen.avg_time_per_text_ms, 2))ms"
                Write-Host "    Device: $($embGen.device_used)"
            }

            if ($benchmark.benchmarks.semantic_search) {
                $semSearch = $benchmark.benchmarks.semantic_search
                Write-Host "  Semantic Search:"
                Write-Host "    Documents Searched: $($semSearch.documents_searched)"
                Write-Host "    Results Returned: $($semSearch.results_returned)"
                Write-Host "    Total Time: $([math]::Round($semSearch.total_time_ms, 2))ms"
                Write-Host "    Device: $($semSearch.device_used)"
            }
        } catch {
            Write-Warning "Benchmark failed: $_"
        }
    }

    Write-Host ""
    Write-Success "Health check: PASSED"

} catch {
    Write-Error "HTTP Endpoint: Not responding"
    Write-Host "  Error: $_"
    Write-Host ""
    Write-Warning "Service is running but not responding to HTTP requests"
    Write-Info "Check logs: .\scripts\view-logs.ps1"
    exit 1
}

# Network connectivity check
Write-Host ""
Write-Info "Checking network connectivity..."

# Check backend
$backendHost = "172.16.168.20"
$backendPort = 8001
$backendTest = Test-NetConnection -ComputerName $backendHost -Port $backendPort -WarningAction SilentlyContinue
if ($backendTest.TcpTestSucceeded) {
    Write-Success "Backend: Reachable ($backendHost:$backendPort)"
} else {
    Write-Warning "Backend: Not reachable ($backendHost:$backendPort)"
}

# Check Redis
$redisHost = "172.16.168.23"
$redisPort = 6379
$redisTest = Test-NetConnection -ComputerName $redisHost -Port $redisPort -WarningAction SilentlyContinue
if ($redisTest.TcpTestSucceeded) {
    Write-Success "Redis: Reachable ($redisHost:$redisPort)"
} else {
    Write-Warning "Redis: Not reachable ($redisHost:$redisPort)"
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Health Check Complete" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
