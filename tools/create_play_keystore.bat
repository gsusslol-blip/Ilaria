@echo off
title [ILARIA] - Crear keystore Play Store
chcp 65001 >nul
cd /d "%~dp0\.."

set "JAVA_HOME=C:\Program Files\Microsoft\jdk-17.0.20.8-hotspot"
set "Path=%JAVA_HOME%\bin;%Path%"

if not exist "%JAVA_HOME%\bin\keytool.exe" (
  echo [!] Falta keytool ^(OpenJDK 17^).
  exit /b 1
)

if not exist "secrets" mkdir secrets

if exist "secrets\ilaria-release.jks" (
  echo [!] Ya existe secrets\ilaria-release.jks — no se sobrescribe.
  echo     Si perdés esta clave, NO podés actualizar la app en Play con el mismo applicationId.
  exit /b 0
)

echo.
echo Vas a crear el keystore de release. ANOTÁ las contraseñas en un lugar seguro.
echo Alias fijo: ilaria
echo.
keytool -genkeypair -v ^
  -keystore "secrets\ilaria-release.jks" ^
  -alias ilaria ^
  -keyalg RSA ^
  -keysize 2048 ^
  -validity 10000 ^
  -storetype JKS

if errorlevel 1 (
  echo [!] keytool falló
  exit /b 1
)

if not exist "android\keystore.properties" (
  copy /Y "android\keystore.properties.example" "android\keystore.properties" >nul
  echo [+] Creé android\keystore.properties — editá storePassword y keyPassword.
) else (
  echo [i] android\keystore.properties ya existe — revisá que apunte a ../secrets/ilaria-release.jks
)

echo.
echo [+] Keystore: secrets\ilaria-release.jks
echo     Backup obligatorio ^(USB / nube cifrada^). Sin esto no hay updates en Play.
echo     Luego: editá android\keystore.properties y corre build-play.bat
echo.
exit /b 0
