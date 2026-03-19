# Setup rapide - cree le fichier .env avec les cles API
$envFile = Join-Path $PSScriptRoot ".env"

if (Test-Path $envFile) {
    Write-Host "Le fichier .env existe deja." -ForegroundColor Yellow
} else {
    Write-Host "=== Configuration des cles API ===" -ForegroundColor Cyan
    Write-Host ""

    $anthropicKey = Read-Host "Collez votre cle API Anthropic (sk-ant-...)"

    $content = @"
FRANCE_TRAVAIL_CLIENT_ID=PAR_claudecode_f6055c565edf1a6a9c27d84c0b8a62f09173ee5700aebba92f89eb33bcf7e205
FRANCE_TRAVAIL_CLIENT_SECRET=cae6fa43136ebb901a0f220eed48394b2459a8bd32ce1fa4a3ef32a7a8f7420f
ANTHROPIC_API_KEY=$anthropicKey
"@
    Set-Content -Path $envFile -Value $content -Encoding UTF8
    Write-Host "Fichier .env cree avec succes !" -ForegroundColor Green
}

# Installer les dependances
Write-Host "Installation des dependances..." -ForegroundColor Cyan
python -m pip install -r (Join-Path $PSScriptRoot "requirements.txt")

Write-Host ""
Write-Host "Setup termine ! Lancez : python -m job_agent search" -ForegroundColor Green
