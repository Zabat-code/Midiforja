@echo off
REM ============================================================================
REM  build_audiveris.bat - Compila el Audiveris vendoreado (audiveris-master/)
REM  como motor self-contained de Midiforja (OMR de partituras).
REM
REM  IMPORTANTE: la rama master de Audiveris requiere Java 25 (mira
REM  audiveris-master/gradle.properties -> theMinJavaVersion = 25).
REM  El JDK 17 instalado en este equipo NO alcanza para esta rama.
REM
REM  Pasos:
REM   1) Instala un JDK 25 (p.ej. Oracle/Temurin/Azul) y pon JAVA_HOME.
REM   2) Asegura Gradle. Si gradlew no viene con su wrapper (faltan
REM      gradle/wrapper/gradle-wrapper.jar y .properties), instala Gradle
REM      (https://gradle.org) y usa 'gradle' en lugar de '.\gradlew.bat'.
REM   3) Ejecuta este script (prefiere el binario vendoreado que produce).
REM ============================================================================
setlocal
cd /d "%~dp0..\audiveris-master"

echo.
echo [1/3] Comprobando JAVA_HOME / java ...
java -version 2>&1 | findstr /i "version" || (echo  ERROR: no se encontro java. & exit /b 1)

echo.
echo [2/3] Buscando Gradle ...
if exist ".\gradlew.bat" (
  set GRADLE_CMD=.\gradlew.bat
  echo  Usando wrapper gradlew.bat
) else (
  where gradle >nul 2>nul
  if errorlevel 1 (
    echo  ERROR: sin gradlew ni 'gradle' en PATH.
    echo  Instala Gradle o restaura el wrapper en gradle/wrapper/.
    exit /b 1
  )
  set GRADLE_CMD=gradle
)

echo.
echo [3/3] Compilando :app:installDist ...
call %GRADLE_CMD% :app:installDist
if errorlevel 1 (
  echo  ERROR: fallo el build. Revisa JAVA_HOME (requiere JDK 25) y la red.
  exit /b 1
)

echo.
echo  Listo. Binario vendoreado en:
echo    %CD%\app\build\install\audiveris\bin\
echo  server.py ya lo detecta como primera opcion (sin instalacion externa).
endlocal
