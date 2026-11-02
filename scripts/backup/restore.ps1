<#
.SYNOPSIS
Restaura um backup (.dump, formato custom) do banco EcoCiente.

.DESCRIPTION
Banco inteiro: pg_restore --clean --if-exists --no-owner --no-privileges
--exit-on-error. Apaga e recria os objetos do destino.

Tabela isolada (-Tabela): usa --data-only. Sem -Truncar, linhas já existentes
podem colidir com a chave primária. Para recuperar uma exclusão acidental com
segurança, o caminho recomendado é restaurar o dump INTEIRO num banco novo e
copiar de lá as linhas que faltam.

Variáveis de ambiente:
  ECOCIENTE_DSN          origem (usada por -Comparar e para proteger contra
                         restaurar em cima do banco de produção); lida do .env
                         da raiz se não estiver no ambiente
  ECOCIENTE_RESTORE_DSN  destino alternativo ao parâmetro -Destino
  ECOCIENTE_ALLOW_RESET  =1 permite destino igual a ECOCIENTE_DSN
  PG_BIN                 pasta com pg_dump/pg_restore/psql (padrão: PATH)

.PARAMETER Arquivo
Backup .dump gerado por backup.ps1 / backup.sh.

.PARAMETER Destino
DSN do banco de destino (ou variável ECOCIENTE_RESTORE_DSN).

.PARAMETER Tabela
Restaura só estas tabelas (aceita vários valores).

.PARAMETER Truncar
Com -Tabela: esvazia (TRUNCATE) as tabelas antes de restaurar.

.PARAMETER Comparar
Depois de restaurar, compara as contagens com a origem (ECOCIENTE_DSN);
sai com código 1 se alguma divergir.

.PARAMETER Ajuda
Mostra esta ajuda.

.EXAMPLE
.\scripts\backup\restore.ps1 -Comparar backups\ecociente_20260101_120000.dump postgres://u:s@h:5432/ecociente_teste

.EXAMPLE
$env:ECOCIENTE_RESTORE_DSN = 'postgres://u:s@h:5432/novo'; .\scripts\backup\restore.ps1 backups\ecociente_x.dump

.EXAMPLE
.\scripts\backup\restore.ps1 -Tabela tb_cursos -Truncar backups\ecociente_x.dump postgres://u:s@h:5432/ecociente_teste
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)][string]$Arquivo,
    [Parameter(Position = 1)][string]$Destino,
    [Alias('t')][string[]]$Tabela,
    [switch]$Truncar,
    [switch]$Comparar,
    [Alias('h')][switch]$Ajuda
)

$ErrorActionPreference = 'Stop'
if ($Ajuda) { Get-Help $MyInvocation.MyCommand.Path -Detailed; exit 0 }

$Raiz = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path

function Mascarar([string]$d) { [regex]::Replace([regex]::Replace($d, '(://[^:/@]*):[^/]*@', '$1:***@'), '(password=)\S+', '$1***') }
function Falhar([string]$msg, [int]$codigo = 1) {
    [Console]::Error.WriteLine($msg)
    exit $codigo
}

if (-not $Arquivo) { Falhar 'ERRO: informe o arquivo .dump (veja -Ajuda)' 2 }
if (-not (Test-Path -LiteralPath $Arquivo -PathType Leaf)) { Falhar "ERRO: arquivo não encontrado: $Arquivo" }
if (-not $Destino) { $Destino = $env:ECOCIENTE_RESTORE_DSN }
if (-not $Destino) { Falhar 'ERRO: informe o destino (parâmetro -Destino ou ECOCIENTE_RESTORE_DSN)' 2 }
if ($Truncar -and -not $Tabela) { Falhar 'ERRO: -Truncar só vale junto com -Tabela' 2 }
foreach ($t in @($Tabela)) {
    if ($t -and $t -notmatch '^[a-z_][a-z0-9_]*$') { Falhar "ERRO: nome de tabela inválido: $t" 2 }
}

# ---------- conexão de origem ----------
$Dsn = $env:ECOCIENTE_DSN
if ([string]::IsNullOrEmpty($Dsn)) {
    $arqEnv = Join-Path $Raiz '.env'
    if (Test-Path -LiteralPath $arqEnv) {
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
if ([string]::IsNullOrEmpty($Dsn) -and $Comparar) { Falhar 'ERRO: defina ECOCIENTE_DSN (veja .env.example)' }

if ($Dsn -and $Destino -eq $Dsn -and $env:ECOCIENTE_ALLOW_RESET -ne '1') {
    Falhar "ERRO: o destino é igual a ECOCIENTE_DSN ($(Mascarar $Destino)). Recusado para não sobrescrever a origem; defina ECOCIENTE_ALLOW_RESET=1 se for isso mesmo."
}

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
$PgRestore = Achar-Bin 'pg_restore'
$Psql = Achar-Bin 'psql'

$Principais = @('tb_usuarios', 'tb_condominios', 'tb_moradores', 'tb_cooperativas', 'tb_postagens',
    'tb_rel_votos_postagens', 'tb_agendamentos_coletas', 'tb_visitas_coletas', 'tb_cursos', 'tb_aulas',
    'tb_quizzes', 'tb_tentativas_quiz', 'tb_movimentacoes_pontos', 'tb_notificacoes', 'tb_log_auditoria',
    'fato_postagens', 'fato_coletas')

function Sql([string]$dsn, [string]$cmd) {
    $r = & $Psql -X -qtA -d $dsn -c $cmd
    if ($LASTEXITCODE -ne 0) { return $null }
    return ($r | Out-String).Trim()
}
function Existe([string]$dsn, [string]$tab) { (Sql $dsn "SELECT to_regclass('public.$tab') IS NOT NULL") -eq 't' }
function Contar([string]$dsn, [string]$tab) {
    if (Existe $dsn $tab) { Sql $dsn "SELECT count(*) FROM public.$tab" } else { '-' }
}

Write-Host "Arquivo: $Arquivo"
Write-Host "Destino: $(Mascarar $Destino)"

if ((Sql $Destino 'SELECT 1') -ne '1') { Falhar 'ERRO: não foi possível conectar ao destino.' }

$cron = [System.Diagnostics.Stopwatch]::StartNew()
if (-not $Tabela) {
    & $PgRestore --clean --if-exists --no-owner --no-privileges --exit-on-error -d $Destino $Arquivo
    if ($LASTEXITCODE -ne 0) { Falhar "ERRO: pg_restore falhou (código $LASTEXITCODE)." $LASTEXITCODE }
} else {
    foreach ($t in $Tabela) {
        if (-not (Existe $Destino $t)) {
            Falhar "ERRO: a tabela $t não existe no destino. Crie o schema antes (ou restaure o dump inteiro num banco novo)."
        }
    }
    if ($Truncar) {
        $lista = ($Tabela | ForEach-Object { "public.$_" }) -join ', '
        Write-Host "Esvaziando: $lista"
        & $Psql -X -q -v ON_ERROR_STOP=1 -d $Destino -c "TRUNCATE TABLE $lista"
        if ($LASTEXITCODE -ne 0) {
            Falhar 'ERRO: TRUNCATE falhou (chaves estrangeiras de outras tabelas?). Nada foi restaurado.'
        }
    } else {
        Write-Host 'AVISO: sem -Truncar; linhas já existentes podem colidir com a chave primária.'
    }
    $args2 = @('--data-only', '--no-owner', '--no-privileges', '--exit-on-error')
    foreach ($t in $Tabela) { $args2 += @('-t', $t) }
    & $PgRestore @args2 -d $Destino $Arquivo
    if ($LASTEXITCODE -ne 0) { Falhar "ERRO: pg_restore falhou (código $LASTEXITCODE)." $LASTEXITCODE }
}
$cron.Stop()
Write-Host ("Restauração concluída em {0:N1} s" -f $cron.Elapsed.TotalSeconds)

# ---------- contagens ----------
$diverge = $false
if ($Comparar) { Write-Host ('{0,-28} {1,12} {2,12}' -f 'tabela', 'origem', 'restaurado') }
else { Write-Host ('{0,-28} {1,12}' -f 'tabela', 'linhas') }
foreach ($t in $Principais) {
    $dest = Contar $Destino $t
    if ($Comparar) {
        $orig = Contar $Dsn $t
        $marca = ''
        if ($orig -ne $dest) { $marca = '  <-- DIVERGE'; $diverge = $true }
        Write-Host ('{0,-28} {1,12} {2,12}{3}' -f $t, $orig, $dest, $marca)
    } elseif ($dest -ne '-') {
        Write-Host ('{0,-28} {1,12}' -f $t, $dest)
    }
}
if ($Comparar) {
    if ($diverge) { Falhar 'ERRO: contagens divergentes.' }
    Write-Host 'Contagens iguais.'
}
