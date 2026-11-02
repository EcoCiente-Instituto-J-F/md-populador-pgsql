<#
.SYNOPSIS
Backup do banco EcoCiente (pg_dump -Fc + schema.sql) com retenção diária/semanal.

.DESCRIPTION
Gera ecociente_<AAAAMMDD_HHMMSS>.dump e .schema.sql na pasta de backups.
Grava primeiro em .parcial e só renomeia se o pg_dump terminar com código 0.

Variáveis de ambiente:
  ECOCIENTE_DSN                 DSN do banco (ou linha ECOCIENTE_DSN= do .env na raiz)
  ECOCIENTE_BACKUP_DIR          pasta de saída (padrão: <raiz>\backups)
  ECOCIENTE_RETENCAO_DIARIOS    backups mais novos mantidos (padrão: 7)
  ECOCIENTE_RETENCAO_SEMANAIS   semanas ISO adicionais mantidas (padrão: 4)
  PG_BIN                        pasta com pg_dump/pg_restore/psql (padrão: PATH)

.PARAMETER Ajuda
Mostra esta ajuda.

.EXAMPLE
.\scripts\backup\backup.ps1

.EXAMPLE
$env:ECOCIENTE_RETENCAO_DIARIOS = '3'; .\scripts\backup\backup.ps1
#>
[CmdletBinding()]
param([Alias('h')][switch]$Ajuda)

$ErrorActionPreference = 'Stop'
if ($Ajuda) { Get-Help $MyInvocation.MyCommand.Path -Detailed; exit 0 }

$Raiz = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path

function Mascarar([string]$d) { [regex]::Replace([regex]::Replace($d, '(://[^:/@]*):[^/]*@', '$1:***@'), '(password=)\S+', '$1***') }

function Falhar([string]$msg, [int]$codigo = 1) {
    [Console]::Error.WriteLine($msg)
    exit $codigo
}

# ---------- conexão ----------
$Dsn = $env:ECOCIENTE_DSN
if ([string]::IsNullOrEmpty($Dsn)) {
    $arqEnv = Join-Path $Raiz '.env'
    if (Test-Path -LiteralPath $arqEnv) {
        # lê só a linha ECOCIENTE_DSN= (sem executar o .env)
        $linha = Get-Content -LiteralPath $arqEnv -Encoding UTF8 |
            Where-Object { $_ -match '^\s*ECOCIENTE_DSN=' } | Select-Object -Last 1
        if ($linha) {
            $Dsn = ($linha -replace '^\s*ECOCIENTE_DSN=', '').Trim()
            if ($Dsn.Length -ge 2 -and ($Dsn[0] -eq '"' -or $Dsn[0] -eq "'") -and $Dsn[$Dsn.Length - 1] -eq $Dsn[0]) {
                $Dsn = $Dsn.Substring(1, $Dsn.Length - 2)
            }
        }
    }
}
if ([string]::IsNullOrEmpty($Dsn)) { Falhar 'ERRO: defina ECOCIENTE_DSN (veja .env.example)' }

# ---------- binários ----------
function Achar-Bin([string]$nome) {
    if ($env:PG_BIN) {
        foreach ($c in @((Join-Path $env:PG_BIN "$nome.exe"), (Join-Path $env:PG_BIN $nome))) {
            if (Test-Path -LiteralPath $c -PathType Leaf) { return $c }
        }
        Falhar "ERRO: '$nome' não encontrado em PG_BIN=$($env:PG_BIN). Instale o cliente PostgreSQL (versão >= à do servidor; a Aiven usa PG 16+) ou corrija PG_BIN."
    }
    $cmd = Get-Command $nome -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($cmd) { return $cmd.Source }
    Falhar "ERRO: '$nome' não encontrado no PATH. Instale o cliente PostgreSQL (versão >= à do servidor; a Aiven usa PG 16+) ou defina PG_BIN."
}
$PgDump = Achar-Bin 'pg_dump'

# ---------- saída ----------
$Dir = if ($env:ECOCIENTE_BACKUP_DIR) { $env:ECOCIENTE_BACKUP_DIR } else { Join-Path $Raiz 'backups' }
$NDia = if ($env:ECOCIENTE_RETENCAO_DIARIOS) { $env:ECOCIENTE_RETENCAO_DIARIOS } else { '7' }
$NSem = if ($env:ECOCIENTE_RETENCAO_SEMANAIS) { $env:ECOCIENTE_RETENCAO_SEMANAIS } else { '4' }
if ($NDia -notmatch '^\d+$' -or $NSem -notmatch '^\d+$') { Falhar 'ERRO: retenção deve ser número inteiro (ECOCIENTE_RETENCAO_DIARIOS >= 1, ECOCIENTE_RETENCAO_SEMANAIS >= 0)' }
$NDia = [int]$NDia; $NSem = [int]$NSem
if ($NDia -lt 1) { Falhar 'ERRO: ECOCIENTE_RETENCAO_DIARIOS deve ser >= 1 (a retenção nunca pode apagar o backup recém-criado)' }
New-Item -ItemType Directory -Force -Path $Dir | Out-Null

$Carimbo = Get-Date -Format 'yyyyMMdd_HHmmss'
while (Test-Path -LiteralPath (Join-Path $Dir "ecociente_$Carimbo.dump")) {
    Start-Sleep -Seconds 1
    $Carimbo = Get-Date -Format 'yyyyMMdd_HHmmss'
}
$Dump = Join-Path $Dir "ecociente_$Carimbo.dump"
$Schema = Join-Path $Dir "ecociente_$Carimbo.schema.sql"

Write-Host "Banco: $(Mascarar $Dsn)"
$cron = [System.Diagnostics.Stopwatch]::StartNew()

# grava em .parcial e só renomeia se o pg_dump terminar com código 0
function Executar([string]$final, [string[]]$extra) {
    $parcial = "$final.parcial"
    & $PgDump @extra --no-owner --no-privileges -f $parcial $Dsn | Out-Null
    $cod = $LASTEXITCODE
    if ($cod -ne 0) {
        Remove-Item -LiteralPath $parcial -Force -ErrorAction SilentlyContinue
        [Console]::Error.WriteLine("ERRO: pg_dump falhou (código $cod). Nenhum backup novo foi gravado.")
        return $false
    }
    Move-Item -LiteralPath $parcial -Destination $final -Force
    return $true
}

if (-not (Executar $Dump @('-Fc'))) { exit 1 }
if (-not (Executar $Schema @('--schema-only'))) {
    Remove-Item -LiteralPath $Dump -Force -ErrorAction SilentlyContinue
    exit 1
}
$cron.Stop()

function MB([string]$arq) { '{0:N1}' -f ((Get-Item -LiteralPath $arq).Length / 1MB) }
function Rel([string]$arq) {
    if ($arq.StartsWith($Raiz)) { $arq.Substring($Raiz.Length).TrimStart('\', '/') } else { $arq }
}
Write-Host ("ok: {0} ({1} MB) em {2:N1} s" -f (Rel $Dump), (MB $Dump), $cron.Elapsed.TotalSeconds)
Write-Host ("ok: {0} ({1} MB)" -f (Rel $Schema), (MB $Schema))

# ---------- retenção (só após sucesso) ----------
function Semana-Iso([string]$ymd) {
    $dt = [datetime]::ParseExact($ymd, 'yyyyMMdd', [Globalization.CultureInfo]::InvariantCulture)
    $ano = [System.Globalization.ISOWeek]::GetYear($dt)
    $sem = [System.Globalization.ISOWeek]::GetWeekOfYear($dt)
    '{0}-{1:00}' -f $ano, $sem
}
function Semana-Iso-Compat([string]$ymd) {
    if ('System.Globalization.ISOWeek' -as [type]) { return (Semana-Iso $ymd) }
    # Windows PowerShell 5.1 (.NET Framework) não tem ISOWeek: cálculo manual
    $dt = [datetime]::ParseExact($ymd, 'yyyyMMdd', [Globalization.CultureInfo]::InvariantCulture)
    $dia = [int]$dt.DayOfWeek; if ($dia -eq 0) { $dia = 7 }
    $quinta = $dt.AddDays(4 - $dia)
    $sem = [int][math]::Floor(($quinta.DayOfYear - 1) / 7) + 1
    '{0}-{1:00}' -f $quinta.Year, $sem
}

$todos = @(Get-ChildItem -LiteralPath $Dir -File |
    Where-Object { $_.Name -match '^ecociente_\d{8}_\d{6}\.dump$' } |
    Sort-Object Name -Descending | ForEach-Object { $_.Name })
$manter = New-Object System.Collections.Generic.List[string]
$apagar = New-Object System.Collections.Generic.List[string]
$vistas = New-Object System.Collections.Generic.List[string]
$i = 0
foreach ($f in $todos) {
    $i++
    if ($i -le $NDia) { $manter.Add($f); continue }
    $sem = Semana-Iso-Compat $f.Substring(10, 8)
    if (-not $vistas.Contains($sem) -and $vistas.Count -lt $NSem) {
        $vistas.Add($sem); $manter.Add($f)
    } else {
        $apagar.Add($f)
    }
}

Write-Host "Retenção (diários=$NDia, semanais=$NSem):"
foreach ($f in $manter) { Write-Host "  mantido: $f" }
foreach ($f in $apagar) {
    $base = $f.Substring(0, $f.Length - 5)
    Remove-Item -LiteralPath (Join-Path $Dir $f) -Force
    Remove-Item -LiteralPath (Join-Path $Dir "$base.schema.sql") -Force -ErrorAction SilentlyContinue
    Write-Host "  apagado: $f (e $base.schema.sql)"
}
