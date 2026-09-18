# Play Store y portable

Hay **dos entregas**. No es el mismo binario.

## 1. Portable Windows (PC)

1. `run.bat` → HUD local
2. Distribución: `build.bat` → `dist\`

## 2. Android sideload (LAN / WAN, sin Play)

```bat
build-apk.bat
```

Salida: `dist\Ilaria-android.apk` (debug). También en GitHub Releases.

## 3. Google Play Store (público, firmado)

### Una sola vez

1. Cuenta en [Play Console](https://play.google.com/console) (~25 USD).
2. Hosteá `docs/privacy.html` en **HTTPS** (GitHub Pages / Netlify) y guardá la URL.
3. Creá el keystore (no se sube a Git):

```bat
tools\create_play_keystore.bat
```

4. Editá `android\keystore.properties` (copiado del `.example`) con las contraseñas reales.

### Cada release

```bat
build-play.bat
```

Salida: `dist\Ilaria-play.aab`

En Play Console:

1. App nueva **Ilaria** (`app.gsuss.asistente`)
2. Producción o **Prueba interna** → subir el `.aab`
3. Ficha: ícono, capturas, descripción (dejar claro: necesita la PC con Ilaria en LAN/WAN)
4. **Data safety** + URL de privacidad
5. Enviar a revisión

### Seguridad del keystore

- `secrets/ilaria-release.jks` y `android/keystore.properties` están en `.gitignore`
- Si perdés el `.jks`, **no podés actualizar** la misma app en Play
- Hacé backup cifrado ya

### Notas de revisión Google

- La app es cliente del asistente en **tu PC** (no SaaS propio): decilo en la descripción
- Evitá marcas de terceros (JARVIS, etc.)
- El APK debug de Releases **no** sirve para Play; usá siempre el `.aab` de `build-play.bat`
