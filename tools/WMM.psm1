<#
  PowerShell module for the Windows Maintenance Manager API (2.10). Create an API token in the console
  (Settings › My account › API tokens), then:
    Import-Module .\tools\WMM.psm1
    Connect-Wmm -Token wmm_0123…            # or $env:WMM_TOKEN
    Get-WmmHealth
    Get-WmmTool -Kind report | Select-Object id, title
    Start-WmmRun -Tool network.flush_dns -Reason "TICKET-42" -Wait
    Get-WmmIncident -Status open
    Get-WmmAudit -Action login. -Last 20
  The token acts as its user, limited to its scopes, and works only on this PC (127.0.0.1).
#>
$script:WmmBase = "http://127.0.0.1:8765/api/v1"
$script:WmmToken = $env:WMM_TOKEN

function Connect-Wmm {
  param([Parameter(Mandatory)][string]$Token, [int]$Port = 8765)
  if ($Token -notmatch '^wmm_[0-9a-f]{40}$') { throw "This is not a Windows Maintenance Manager API token." }
  $script:WmmToken = $Token
  $script:WmmBase = "http://127.0.0.1:$Port/api/v1"
  Invoke-WmmApi GET /auth/me | Select-Object username, role
}

function Invoke-WmmApi {
  param([Parameter(Mandatory)][ValidateSet("GET", "POST", "PUT", "PATCH", "DELETE")][string]$Method, [Parameter(Mandatory)][string]$Path, $Body)
  if (-not $script:WmmToken) { throw "Run Connect-Wmm -Token <token> first." }
  $p = @{ Method = $Method; Uri = "$script:WmmBase$Path"; Headers = @{ Authorization = "Bearer $script:WmmToken" }; ContentType = "application/json" }
  if ($null -ne $Body) { $p.Body = ($Body | ConvertTo-Json -Depth 8 -Compress) }
  try { Invoke-RestMethod @p } catch {
    $msg = $_.ErrorDetails.Message
    if ($msg) { try { $msg = ($msg | ConvertFrom-Json).error } catch {} }
    throw "WMM $Method $Path failed: $(if ($msg) { $msg } else { $_.Exception.Message })"
  }
}

function Get-WmmHealth { Invoke-WmmApi GET /dashboard }
function Get-WmmTool { param([ValidateSet("", "fix", "report")][string]$Kind = "", [string]$Search = "")
  $q = @(); if ($Kind) { $q += "kind=$Kind" }; if ($Search) { $q += "q=$([uri]::EscapeDataString($Search))" }
  (Invoke-WmmApi GET ("/actions" + $(if ($q) { "?" + ($q -join "&") } else { "" }))).actions }
function Start-WmmRun {
  param([Parameter(Mandatory)][string[]]$Tool, [string]$Reason = "", [switch]$Confirm, [switch]$Wait)
  $r = Invoke-WmmApi POST /runs @{ actions = $Tool; confirmed = [bool]$Confirm; reason = $Reason }
  if ($r.approval) { Write-Warning "Waiting for the approval of a second person (request $($r.approval.id))."; return $r.approval }
  if (-not $Wait) { return $r }
  do { Start-Sleep -Seconds 2; $s = Invoke-WmmApi GET "/runs/$($r.id)" } while ($s.active)
  $s.results
}
function Get-WmmHistory { param([int]$Last = 50) (Invoke-WmmApi GET "/history?limit=$Last").runs }
function Get-WmmIncident { param([ValidateSet("", "open", "acknowledged", "closed")][string]$Status = "")
  (Invoke-WmmApi GET ("/incidents" + $(if ($Status) { "?status=$Status" } else { "" }))).incidents }
function Set-WmmIncident { param([Parameter(Mandatory)][string]$Id, [Parameter(Mandatory)][ValidateSet("ack", "close", "reopen")][string]$Action, [string]$Note = "")
  Invoke-WmmApi POST "/incidents/$Id/$Action" @{ note = $Note } }
function Get-WmmAudit { param([string]$Action = "", [string]$User = "", [int]$Last = 100)
  $q = "limit=$Last"; if ($Action) { $q += "&action=$([uri]::EscapeDataString($Action))" }; if ($User) { $q += "&user=$([uri]::EscapeDataString($User))" }
  (Invoke-WmmApi GET "/audit?$q").entries }
function Get-WmmCentralPc { param([string]$Group = "") (Invoke-WmmApi GET ("/central" + $(if ($Group) { "?group=$([uri]::EscapeDataString($Group))" } else { "" }))).agents }
function Send-WmmCentralJob {
  param([Parameter(Mandatory)][ValidateSet("actions", "winget", "policy", "baseline", "inventory")][string]$Kind, [hashtable]$Payload = @{},
        [string[]]$Pc = @(), [string]$Group = "")
  Invoke-WmmApi POST /central/jobs @{ kind = $Kind; payload = $Payload; agents = $Pc; group = $Group } }

Export-ModuleMember -Function Connect-Wmm, Invoke-WmmApi, Get-WmmHealth, Get-WmmTool, Start-WmmRun, Get-WmmHistory, Get-WmmIncident, Set-WmmIncident,
  Get-WmmAudit, Get-WmmCentralPc, Send-WmmCentralJob
