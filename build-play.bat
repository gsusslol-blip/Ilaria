@echo off
title [ILARIA] - Play Store App Bundle (.aab)
chcp 65001 >nul
cd /d "%~dp0"

set "JAVA_HOME=C:\Program Files\Microsoft\jdk-17.0.20.8-hotspot"
set "ANDROID_HOME=%~dp0.android-sdk"
set "ANDROID_SDK_ROOT=%ANDROID_HOME%"
set "Path=%JAVA_HOME%\bin;%Path%"

if not exist "%JAVA_HOME%\bin\java.exe" (
  echo [!] Falta OpenJDK 17. Instala: winget install Microsoft.OpenJDK.17
  exit /b 1
)
if not exist "%ANDROID_HOME%\platforms\android-35" (
  echo [!] Falta el SDK en .android-sdk ^(platforms;android-35^).
  exit /b 1
)

powershell -NoProfile -Command ^
  "$p=([IO.Path]::GetFullPath('%~dp0.android-sdk')).TrimEnd('\').Replace('\','\\'); [IO.File]::WriteAllText('%~dp0android\local.properties', 'sdk.dir='+$p+[Environment]::NewLine)"

if not exist "%~dp0android\keystore.properties" (
  echo [!] Falta android\keystore.properties
  echo     1^) Corre: tools\create_play_keystore.bat
  echo     2^) Copiá android\keystore.properties.example -^> android\keystore.properties
  echo     3^) Completá storePassword / keyPassword
  exit /b 2
)
if not exist "%~dp0secrets\ilaria-release.jks" (
  echo [!] Falta secrets\ilaria-release.jks
  echo     Corre: tools\create_play_keystore.bat
  exit /b 2
)

echo [+] Compilando App Bundle firmado ^(Play Store^)...
cd /d "%~dp0android"
call gradlew.bat bundleRelease --no-daemon
if errorlevel 1 (
  echo [!] Fallo bundleRelease
  exit /b 1
)

if not exist "%~dp0dist" mkdir "%~dp0dist"
copy /Y "%~dp0android\app\build\outputs\bundle\release\app-release.aab" "%~dp0dist\Ilaria-play.aab" >nul
echo.
echo [+] Listo: dist\Ilaria-play.aab
echo     Subilo en Play Console -^> Producción / Prueba interna.
echo     Privacidad HTTPS: hosteá docs\privacy.html ^(GitHub Pages^).
echo.
exit /b 0
