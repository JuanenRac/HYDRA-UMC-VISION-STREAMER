<p align="center">
  <img src="images/HYDRA_UMC_BANNER.svg" alt="HYDRA-UMC-VISION-STREAMER banner" width="100%">
</p>

# 📹 HYDRA-UMC-VISION-STREAMER

<p align="center"><a href="README.md">🇺🇸 English</a> | <a href="README_spa.md">🇪🇸 Español</a> | <a href="README_fra.md">🇫🇷 Français</a> | <a href="README_ita.md">🇮🇹 Italiano</a> | 🇩🇪 <b>Deutsch</b> | <a href="README_zho.md">🇨🇳 简体中文</a> | <a href="README_jpn.md">🇯🇵 日本語</a></p>

### 🚀 Optimierte GStreamer-Pipeline für Multi-Kamera-Edge-KI

<p align="left">
  <img src="https://img.shields.io/badge/Lizenz-GPL%203.0-blue.svg" alt="GPL 3.0">
  <img src="https://img.shields.io/badge/Framework-GStreamer-62B417.svg" alt="GStreamer">
  <img src="https://img.shields.io/badge/Plattform-Raspberry%20Pi%20CM5-BC1142.svg" alt="CM5">
  <img src="https://img.shields.io/badge/Schnittstelle-8x%20USB%203.0-blue.svg" alt="8x USB 3.0">
  <img src="https://img.shields.io/badge/Stufe-Funktional%20v0-green.svg" alt="Funktional v0">
</p>

---

## 1. 🛠️ TECHNISCHER ÜBERBLICK

**HYDRA-UMC-VISION-STREAMER** soll die leistungsstarke Medien-Erfassungsschicht der Vision-AI-Node-Familie werden. Seine Aufgabe ist die Erfassung auf niedriger Ebene, Vorverarbeitung und Verteilung von bis zu 8 gleichzeitigen USB-3.0-Kameraströmen, unter Nutzung des hardwarebeschleunigten ISP des Broadcom BCM2712 (CM5) für Farbraumkonvertierung, Skalierung und Normalisierung, bevor Frames die Hailo-8-NPU erreichen.

Dies ist eines der 4 Kind-Projekte von **[HYDRA-UMC-VISION-NODE](https://github.com/JuanenRac/HYDRA-UMC-VISION-NODE)**, dem Integrations-Elternteil der Familie: Dieses Projekt besitzt nur Erfassung/Vorverarbeitung und führt weder eigene Hailo-8-Inferenz noch eine gRPC-API oder Sicherheitslogik aus - das ist bewusst auf seine 3 Geschwister verteilt.

### Kernpunkte

* ✅ **Echtes v0 - Config-, Pipeline- und Relay-Generierung:** `config.py` validiert eine JSON-Konfiguration pro Kamera (Gerät, Auflösung, fps, Format); `pipeline.py` generiert die exakte GStreamer-Pipeline-Beschreibung für eine Kamera; `mediamtx_config.py` generiert die passende MediaMTX-`paths.yml`. Über `config validate`/`config gst`/`config mediamtx` unten verfügbar - kein GStreamer-Laufzeitsystem, V4L2 oder physische Kamera nötig, um es auszuführen oder zu testen.
* 🔁 **Echtes v0 - Begrenzte Pufferung und Wiederverbindung:** `FrameBuffer` in `buffer.py` ist eine Warteschlange fester Kapazität, die beim Vollsein das ÄLTESTE Element verwirft (nie das neueste) - die echte Backpressure-Politik, die ein Live-Relay braucht, damit ein langsamer Konsument den Speicher dieses Prozesses niemals unbegrenzt wachsen lassen kann. `ConnectionTracker` in `reconnect.py` ist eine echte, deterministische Wiederverbindungspolitik mit exponentiellem Backoff für eine abgebrochene Kamera-/Relay-Verbindung. Über `stream simulate` unten verfügbar - vollständig testbar ohne GStreamer oder physische Kamera.
* 📡 **RTSP/WebRTC-Unterstützung (teilweise geplant):** der RTSP-Relay-Pfad (`rtspclientsink` → MediaMTX) ist entworfen und seine Konfiguration wird oben real generiert; ihn tatsächlich auszuführen benötigt das GStreamer-Laufzeitsystem, das diese Umgebung nicht hat. Die WebRTC-Ausgabe bleibt vollständig geplant.
* 🔌 **HailoRT-Integrationsgrenze, dem Modul vorausgehend vorbereitet:** `hailo_runtime.py` ist gegen die echte, bestätigte `hailo_platform`-API (`VDevice`, `HEF`, `ConfigureParams`) geschrieben - lazy importiert, sodass dieses Repository ohne installiertes `hailort`-Paket oder vorhandenes Hailo-8-Modul sauber installiert/getestet wird - plus eine echte Preflight-Validierung, dass die konfigurierte Auflösung einer Kamera tatsächlich mit der Eingabe-Tensor-Form eines geladenen Modells übereinstimmt, bevor auch nur ein einziges Frame an das Gerät gesendet wird. *(implementiert, nur Integrationsgrenze - tatsächliche Inferenz auszuführen und die echte NMS-Ausgabe eines Modells zu parsen ist weiterhin zukünftige Arbeit.)*
* ⚡ **Zero-Copy-Pipeline (geplant):** Buffer-Übergabe zwischen V4L2 und HailoRT, entworfen, um unnötige Frame-Kopien zu vermeiden. *(zukünftige Arbeit - benötigt das echte V4L2/HailoRT-Laufzeitsystem, das diese Umgebung nicht hat.)*
* 🌈 **Hardware-Vorverarbeitung (geplant):** Echtzeit-Skalierung und Pixelformatkonvertierung über den ISP der Pi, wodurch Arbeit von der CPU genommen wird, die sonst pro Frame anfiele. *(zukünftige Arbeit, gleicher Grund.)*
* 🛠️ **Dynamische Konfiguration:** Auflösung, Framerate und Pixelformat pro Kamera sind heute real und werden validiert (`config.py`); die Belichtungs-/Verstärkungssteuerung benötigt das echte V4L2-Gerät und ist zukünftige Arbeit.
* 🧩 **Warum als eigenes Projekt:** Erfassungs-/ISP-Abstimmung ist eine andere Fähigkeit und eine andere Fehlerdomäne als Modellinferenz oder Sicherheitslogik - sie im eigenen Prozess zu halten bedeutet, dass ein Erfassungsfehler [HYDRA-UMC-SAFETY-ZONES](https://github.com/JuanenRac/HYDRA-UMC-SAFETY-ZONES) nicht lahmlegen kann, und beide können unabhängig entwickelt/getestet werden.

**Ehrlichkeitscheck - was heute wirklich läuft:** die Konfigurationsvalidierung, die Generierung der GStreamer-Pipeline-Beschreibung, die Generierung der MediaMTX-Relay-Konfiguration, und die echte Puffer-/Wiederverbindungspolitik, und eine echte HailoRT-Integrationsgrenze (`config.py`, `pipeline.py`, `mediamtx_config.py`, `buffer.py`, `reconnect.py`, `hailo_runtime.py`) sind real und getestet (65 Tests). Nichts davon öffnet ein V4L2-Gerät, importiert GStreamer oder spricht mit einer physischen Kamera - die generierte Pipeline tatsächlich auszuführen benötigt dieses echte Laufzeitsystem und diese echte Hardware, die diese Umgebung nicht hat. Siehe [`CHANGELOG.md`](CHANGELOG.md) für genau das, was bisher geliefert wurde, und "Aktueller Status & Nächste Schritte" unten für das, was noch offen ist.

---

## 2. 🔄 GEPLANTE PIPELINE-ARCHITEKTUR

Das Diagramm unten ist der Ziel-Datenfluss, auf den dieses Projekt hinarbeitet - seine *Form* (welches Element welches speist, die `Tee`-Verzweigung) ist durch `pipeline.py` festgelegt und wird heute als reale `gst-launch-1.0`-Syntax generiert, aber nichts in diesem Diagramm läuft bereits: das benötigt das echte V4L2/GStreamer/Hailo-8-Laufzeitsystem und physische USB-Kameras.

```mermaid
graph LR
    USB[8x USB-Kameras] --> V4L2[V4L2-Erfassung]
    V4L2 --> ISP[Hardware-ISP<br/>Skalierung/Format]
    ISP --> TEE[Tee-Element]
    TEE --> HAI[Hailo-NPU-Inferenz]
    TEE --> DISP[Lokale Anzeige / Stream]
```

---

## 3. 🧠 ERWEITERTE TECHNISCHE INFORMATIONEN

### Warum es hier kein `hardware/`, `firmware/`, `os/` oder `models/` gibt

CM5 + Hailo-8 ist handelsübliche Hardware ohne eigenes zu entwerfendes Board, anders als die kundenspezifischen STM32H745/STM32G474-Boards in [HYDRA-UMC](https://github.com/JuanenRac/HYDRA-UMC) - daher existiert in keinem der 5 Vision-AI-Node-Projekte ein `hardware/`/`firmware/`-Ordner. `os/` (das gemeinsame HydraOS-Abbild) und `models/` (die zur Laufzeit tatsächlich an die NPU ausgelieferten kompilierten `.hef`-Dateien) leben nur im Integrations-Elternteil, [HYDRA-UMC-VISION-NODE](https://github.com/JuanenRac/HYDRA-UMC-VISION-NODE), da dieser der Prozess ist, dem das CM5-Host-Abbild und das Hailo-8-Gerätehandle gehören - separate Kopien hier zu führen wäre nur zusätzlicher, nutzloser Synchronisationsaufwand.

### Geplante Pipeline-Form

Das `Tee`-Element im obigen Diagramm ist die zentrale, bereits vor der Implementierung getroffene Designentscheidung: erfasste/vorverarbeitete Frames sollen gleichzeitig zu zwei Abnehmern verzweigen - dem Hailo-8-Inferenzpfad (der [HYDRA-UMC-VISION-NODE](https://github.com/JuanenRac/HYDRA-UMC-VISION-NODE) speist) und einem optionalen lokalen/RTSP-WebRTC-Stream zur menschlichen Überwachung - ohne dass der Überwachungspfad dem Inferenzpfad Latenz hinzufügt.

### Bereits getroffene Designentscheidungen

* **Die Version wird aus den Metadaten des installierten Pakets gelesen, nicht fest codiert** - `main.py` ruft `importlib.metadata.version("hydra-umc-vision-streamer")` statt einer zweiten `__version__`-Zeichenkette auf, sodass `bump_version.py` nur eine Stelle zu bearbeiten hat und beide nie auseinanderlaufen können.
* **Der "Kilometerzähler"-Bump berührt automatisch nur `PATCH`/`MINOR`** - `bump_version.py` überträgt `PATCH` auf `MINOR` über 9 hinaus und `MINOR` auf `MAJOR` über 9 hinaus, erhöht aber nie `MAJOR` selbst; das ist eine bewusste menschliche Entscheidung, dieselbe Konvention wie `HYDRA-UMC-EDITOR-URDF/bump_version.py` und `HYDRA-UMC-SUITE/bump_version.py`.
* **Das MediaMTX-YAML ist handgeschrieben, nicht auf PyYAML aufgebaut** - die Ausgabeform von `mediamtx_config.py` (eine flache `paths:`-Map, ein `source: publisher`-Eintrag pro Kamera) ist einfach und fest genug, dass eine echte Abhängigkeit noch nicht gerechtfertigt ist. Zu überdenken, falls die Konfiguration pro Kamera verschachtelte oder listenwertige Felder erhält.
* **Pipeline und MediaMTX-Konfiguration müssen sich auf einen RTSP-Pfad pro Kamera einigen** - `rtsp_url_for()` ist die einzige Stelle, die ihn ableitet (aus dem Kameranamen), sodass `config gst` und `config mediamtx` nie uneinig darüber sein können, wo der Stream einer Kamera liegt.
* **`FrameBuffer` verwirft das älteste Element, nicht das neueste, wenn voll.** Live-Video hat keinerlei Nutzen für einen wachsenden Rückstand veralteter Frames - das frischeste Frame ist immer das nützliche. Eine Warteschlange, die stattdessen Produzenten blockieren würde, würde den echten Erfassungs-Thread selbst gefährden, und eine Warteschlange, die einfach weiterwächst, würde genau das unbegrenzte Speicherversagen riskieren, das dieses Gate verhindern soll.
* **`reconnect.py` schläft nie und berührt nie selbst einen echten Socket.** `ConnectionTracker` verfolgt nur den Zustand und gibt zurück, wie lange ein Aufrufer warten soll - diese Trennung macht den gesamten Backoff-Zeitplan (einschließlich des ehrlichen Aufgebens nach `max_attempts`) in einem Test exakt reproduzierbar, ohne echte Uhr oder echte Kameraverbindung.

---

## 📂 VERZEICHNISSTRUKTUR

```text
HYDRA-UMC-VISION-STREAMER/
├── src/                 # Quellcode (Paket hydra_umc_vision_streamer)
│   └── hydra_umc_vision_streamer/
│       ├── config.py           # Parsen/Validierung der Konfiguration pro Kamera
│       ├── pipeline.py         # Generierung der GStreamer-Pipeline-Beschreibung
│       ├── buffer.py           # Echter begrenzter Puffer (drop-oldest Backpressure)
│       ├── reconnect.py        # Echte deterministische Wiederverbindungs-/Backoff-Politik
│       ├── mediamtx_config.py  # Generierung der MediaMTX-paths.yml
│       ├── hailo_runtime.py    # Echte HailoRT-Integrationsgrenze (hailo_platform), lazy importiert
│       ├── mjpeg_server.py     # Echter MJPEG-Server - liefert tatsächlich das Bild einer USB-Webcam per HTTP
│       └── main.py             # CLI-Einstiegspunkt (nackter Aufruf + `config`/`stream`)
├── tests/               # Echte pytest-Suite (config, pipeline, mediamtx, buffer, reconnect, hailo_runtime, mjpeg_server, CLI)
├── docs/                # Dokumentation und Tuning-Anleitungen
├── build/               # Build-Ausgabe (hier lebt auch das lokale .venv)
├── images/              # Medien und Diagramme
├── systemd/
│   ├── hydra-umc-vision-streamer@.service  # Pro Kamera instanziierte systemd-Unit
│   └── cameras.env.example                 # Beispiel-Umgebungsdatei pro Instanz
├── tools/
│   ├── build_test.py    # Nicht-versionierender Build-Check
│   └── ci_validate.py   # Manifest/CHANGELOG/Docs-Validierung, von CI genutzt
├── pyproject.toml       # Paketmetadaten, Abhängigkeiten, Kilometerzähler-Version
├── bump_manifest_version.py # Synchronisiert die Version von hydra-umc.project.json mit der nativen (--sync)
├── bump_version.py      # Kilometerzähler-artiger Versions-Bump (build.sh/.bat)
├── build.sh / build.bat # venv + editierbare Installation + Compile-Check + Tests
├── run.sh / run.bat     # Führt den Einstiegspunkt aus dem lokalen venv aus
└── CHANGELOG.md         # Versions-für-Versions-Historie (Kilometerzähler-Schema, ohne Daten)
```

Kein `hardware/`-, `firmware/`-, `os/`- oder `models/`-Ordner - siehe "Erweiterte technische Informationen" oben für das Warum. `os/` und `models/` leben nur im Integrations-Elternteil, [HYDRA-UMC-VISION-NODE](https://github.com/JuanenRac/HYDRA-UMC-VISION-NODE).

---

## 🏗️ BUILD UND AUSFÜHRUNG

### Voraussetzungen

* **Python 3.10 oder neuer** im `PATH` (die Skripte probieren `python3`, dann `python`).
* Kein GStreamer, keine V4L2-Werkzeuge oder andere native Abhängigkeit sind bisher erforderlich - **null Drittanbieter-Laufzeitabhängigkeiten** in dieser Phase (`dependencies = []` in `pyproject.toml`).
* Einige Dutzend MB Festplattenplatz für eine lokale virtuelle Umgebung unter `.venv/`.

### Schritt für Schritt

```bash
# Linux / macOS
./build.sh
```

1. **Kilometerzähler-Versions-Bump** - führt `bump_version.py` aus, das `PATCH` in `pyproject.toml` bei jedem Build erhöht (mit Übertrag auf `MINOR`/`MAJOR` nach obiger Regel).
2. **Virtuelle Umgebung** - erstellt `.venv/`, falls nicht vorhanden; verwendet es sonst weiter.
3. **Editierbare Installation** - `pip install -e ".[dev]"`, sodass Änderungen unter `src/` sofort wirken, installiert `pytest`, und registriert den Konsolen-Einstiegspunkt `hydra-umc-vision-streamer`.
4. **Compile-Check** - `python -m compileall -q src` kompiliert jede Datei unter `src/` zu Bytecode und findet so Syntaxfehler im gesamten Paket.
5. **Echte Test-Suite** - `python -m pytest tests/ -q` (65 Tests, die config, pipeline, MediaMTX-Generierung, die Puffer-/Wiederverbindungspolitik, die HailoRT-Integrationsgrenze und die CLI abdecken).

`set -euo pipefail` stoppt das Skript beim ersten fehlschlagenden Schritt; der Build meldet Erfolg nur, wenn alle 5 Schritte erfolgreich waren.

```bash
./run.sh
```

Sucht den Interpreter innerhalb von `.venv` (unterstützt beide Layouts, POSIX und Windows) und führt `python -m hydra_umc_vision_streamer.main` aus, wobei alle Argumente weitergereicht werden - der nackte Aufruf gibt Name + Version + Rolle aus.

Echtes Beispiel - eine Kamerakonfiguration validieren, ihre GStreamer-Pipeline generieren, und die passende MediaMTX-Relay-Konfiguration generieren:

```bash
./run.sh config validate --config cameras.json
# 2 camera(s) in cameras.json
#   cam0: /dev/video0 1920x1080@30 MJPG
#   cam1: /dev/video1 640x480@15 YUYV
# config OK

./run.sh config gst --config cameras.json --camera cam0
# v4l2src device=/dev/video0 ! image/jpeg,width=1920,height=1080,framerate=30/1 ! jpegdec ! videoconvert ! tee name=t t. ! queue ! appsink name=cam0_hailo_sink t. ! queue ! rtspclientsink location=rtsp://localhost:8554/cam0

./run.sh config mediamtx --config cameras.json
# paths:
#   cam0:
#     source: publisher
#   cam1:
#     source: publisher
```

Echtes Beispiel - simuliert einen langsamen Konsumenten gegen einen begrenzten Puffer, und eine abgebrochene Verbindung, die durch die echte Wiederverbindungspolitik geführt wird:

```bash
./run.sh stream simulate --buffer-size 8 --frames 1000 --consumer-rate 1000
# Pushed 1000 frame(s) through a buffer capped at 8
# Max buffer size observed: 8 (must never exceed 8)
# Frames dropped by backpressure: 972
#
# Simulated disconnect at frame 500
# Reconnect backoff schedule (s): [0.5, 1.0, 2.0, 4.0]
# Final connection state: given_up
```

```bat
:: Windows - gleiche Schritte, Batch-Syntax
build.bat
run.bat
```

### Fehlerbehebung

* **`python`/`python3` nicht gefunden** - Python 3.10+ installieren und sicherstellen, dass es im `PATH` liegt.
* **`compileall` schlägt fehl** - ein echter Syntaxfehler wurde unter `src/` eingeführt; der Build stoppt absichtlich, ohne die Installation anzufassen.
* **"No `.venv` found" von `run.sh`/`run.bat`** - `build.sh`/`build.bat` vorher mindestens einmal ausführen; `run` erstellt die Umgebung nie selbst.
* **Veraltete editierbare Installation** - `.venv/` löschen und neu bauen; selten nötig.

---

## 🚀 Aktueller Status & Nächste Schritte

**Was heute funktioniert:** die Konfigurationsvalidierung, die Generierung der GStreamer-Pipeline-Beschreibung, und die Generierung der MediaMTX-Relay-Konfiguration (`config.py`, `pipeline.py`, `mediamtx_config.py`), ein echter, nachweislich begrenzter Puffer und eine echte deterministische Wiederverbindungspolitik (`buffer.py`, `reconnect.py`, `stream simulate`), eine echte HailoRT-Integrationsgrenze (`hailo_runtime.py`), bereit für ein echtes Hailo-8-Modul, sobald es angeschlossen wird, und ein echter v0-Capture+Serve-Pfad (`mjpeg_server.py`, `stream serve`), der ein echtes V4L2-Gerät über OpenCV öffnet und echtes MJPEG über HTTP ausliefert - installierbar auf einer CM5 über `provisioning/install_vision_streamer.sh` von `HYDRA-UMC-OS` (eine systemd-Instanz pro vom Administrator zugewiesenem Kamera-Slot, `systemd/hydra-umc-vision-streamer@.service`) und bereits live genutzt vom `GET /api/camera/:id/stream`-Proxy von `HYDRA-UMC-SERVER` und den Kameraansichten von `HYDRA-UMC-STUDIO` - 65 Tests insgesamt, plus ein echtes, installierbares Python-Paket mit verifiziertem Einstiegspunkt und ein in den Build integrierter Kilometerzähler-Versions-Bump. Siehe [`CHANGELOG.md`](CHANGELOG.md) für die erfasste Build-/Run-Ausgabe.

**Was noch offen ist, ohne bestimmte Reihenfolge, ohne verbindlichen Zeitplan, und blockiert durch echte Hardware:**

* Die *generierte Pipeline* tatsächlich auszuführen - der vollständige GStreamer/PyGObject-Tee in einen Hailo-8-Inferenzzweig, nicht das einfachere OpenCV-v0 (`stream serve` oben) - über ein echtes Laufzeitsystem.
* Hardware-ISP-Skalierung/Formatkonvertierung (benötigt den echten CM5-ISP).
* Die Inferenz tatsächlich über `hailo_runtime.py` auszuführen (benötigt ein echtes Hailo-8-Modul und eine echte kompilierte `.hef`), und das reale NMS-Ausgabeformat dieses Modells zu parsen - bewusst nicht ohne das Gerät zur Verifikation geraten.
* WebRTC-Ausgabe, und Belichtungs-/Verstärkungssteuerung pro Kamera (benötigt das echte V4L2-Gerät).
* `stream serve` wurde noch nicht gegen eine real angeschlossene USB-Kamera verifiziert - nur gegen ein an der Modulgrenze gemocktes `cv2.VideoCapture` (siehe `tests/test_mjpeg_server.py`).

---

## 🔗 Verwandte Projekte

Dieses Projekt ist Teil eines größeren Robotik-Ökosystems desselben Autors (JuanenRac / Electro Hobby 3D), das Firmware, Steuerungssoftware, KI-Knoten und Flottenwerkzeuge umfasst. Gut zu wissen, denn eine Anfrage könnte sich eigentlich auf eines dieser Projekte statt auf dieses Repository beziehen.

### Familie

**Elternteil:** **[HYDRA-UMC-VISION-NODE](https://github.com/JuanenRac/HYDRA-UMC-VISION-NODE)** — der Integrations-Elternteil, den diese Pipeline speist.

**Geschwister:**
- **[HYDRA-UMC-DETECTION-HEF](https://github.com/JuanenRac/HYDRA-UMC-DETECTION-HEF)** — kompiliert die `.hef`-Modelle, die der Elternteil auf seine Hailo-8-NPU lädt.
- **[HYDRA-UMC-SAFETY-ZONES](https://github.com/JuanenRac/HYDRA-UMC-SAFETY-ZONES)** — wandelt die Wahrnehmung des Elternteils in Eindringlingserkennung und E-STOP-Auslösung um.
- **[HYDRA-UMC-VISUAL-SERVOING-API](https://github.com/JuanenRac/HYDRA-UMC-VISUAL-SERVOING-API)** — wandelt die Wahrnehmung des Elternteils in kinematische Posenkorrekturen um.

Dieses Projekt hat keine direkte Beziehung außerhalb der Vision-AI-Node-Familie (laut der eigenen Beziehungskarte des Ökosystems) - siehe "Restliches Ökosystem" unten für alles andere.

### Restliches Ökosystem

**HYDRA-UMC-Plattform** — die Multi-Roboter-Mikrofabrikzelle
- **[HYDRA-UMC](https://github.com/JuanenRac/HYDRA-UMC)** — das CM5 + STM32H745-Motherboard, das bis zu 8 Roboterarme orchestriert.
- **[HYDRA-UMC-SERVER](https://github.com/JuanenRac/HYDRA-UMC-SERVER)** — das Express/WebSocket-Backend, mit dem jeder Steuerungsclient spricht.
- **[HYDRA-UMC-STUDIO](https://github.com/JuanenRac/HYDRA-UMC-STUDIO)** — webbasiertes Steuerungs-Dashboard, Multi-Roboter-3D-Visualisierung.
- **[HYDRA-UMC-ANDROID-CONTROL](https://github.com/JuanenRac/HYDRA-UMC-ANDROID-CONTROL)** — Android-Steuerungs-App über Wi-Fi/Bluetooth.
- **[HYDRA-UMC-IOS-CONTROL](https://github.com/JuanenRac/HYDRA-UMC-IOS-CONTROL)** — iOS/iPadOS-Steuerungs-App, gebaut in Flutter.
- **[HYDRA-UMC-SUITE](https://github.com/JuanenRac/HYDRA-UMC-SUITE)** — Desktop-Schwarm-Kommandozentrale (Python/PySide6).
- **[HYDRA-UMC-EDITOR-URDF](https://github.com/JuanenRac/HYDRA-UMC-EDITOR-URDF)** — Desktop-URDF-Modelleditor für den Roboterkatalog.
- **[HYDRA-UMC-DSI](https://github.com/JuanenRac/HYDRA-UMC-DSI)** — native Touch-UI für den eingebauten DSI-Touchscreen.

**URTC-Plattform** — der Werkzeugkopf-Controller, den jeder HYDRA-UMC-Roboterarm trägt
- **[URTC](https://github.com/JuanenRac/URTC)** — CAN-Bus-Werkzeugkopf-Controller, 25 Werkzeugprofile.
- **[URTC-FLASHER](https://github.com/JuanenRac/URTC-FLASHER)** — Desktop-Tool für CAN-OTA + SWD/JTAG-Flashing.
- **[URTC-TESTER](https://github.com/JuanenRac/URTC-TESTER)** — Desktop-Tool für Live-CAN-Bus-Diagnose.
- **[URTC-WEB-STUDIO](https://github.com/JuanenRac/URTC-WEB-STUDIO)** — browserbasierte Alternative über die Web-Serial-API.

**🧠 Kognitiver KI-Knoten (Hailo-10)**
- [HYDRA-UMC-COGNITIVE-NODE](https://github.com/JuanenRac/HYDRA-UMC-COGNITIVE-NODE)
- [HYDRA-UMC-VLA-ENGINE](https://github.com/JuanenRac/HYDRA-UMC-VLA-ENGINE)
- [HYDRA-UMC-VOICE-UI](https://github.com/JuanenRac/HYDRA-UMC-VOICE-UI)
- [HYDRA-UMC-SEMANTIC-PLANNER](https://github.com/JuanenRac/HYDRA-UMC-SEMANTIC-PLANNER)
- [HYDRA-UMC-DOCS-QA](https://github.com/JuanenRac/HYDRA-UMC-DOCS-QA)

**🐝 Orchestrierung & Schwarm**
- [HYDRA-UMC-ORCHESTRATOR](https://github.com/JuanenRac/HYDRA-UMC-ORCHESTRATOR)
- [HYDRA-UMC-SWARM-SYNC](https://github.com/JuanenRac/HYDRA-UMC-SWARM-SYNC)
- [HYDRA-UMC-PATH-PLANNER-3D](https://github.com/JuanenRac/HYDRA-UMC-PATH-PLANNER-3D)
- [HYDRA-UMC-JOB-DISPATCHER](https://github.com/JuanenRac/HYDRA-UMC-JOB-DISPATCHER)
- [HYDRA-UMC-NODE-HEALING](https://github.com/JuanenRac/HYDRA-UMC-NODE-HEALING)

**🎮 Digitaler Zwilling & Simulation**
- [HYDRA-UMC-TWIN](https://github.com/JuanenRac/HYDRA-UMC-TWIN)
- [HYDRA-UMC-PHYSICS-REPLICA](https://github.com/JuanenRac/HYDRA-UMC-PHYSICS-REPLICA)
- [HYDRA-UMC-HIL-BRIDGE](https://github.com/JuanenRac/HYDRA-UMC-HIL-BRIDGE)
- [HYDRA-UMC-SYNTHETIC-DATA-GEN](https://github.com/JuanenRac/HYDRA-UMC-SYNTHETIC-DATA-GEN)

**📊 Daten & Analytik**
- [HYDRA-UMC-DATALAKE](https://github.com/JuanenRac/HYDRA-UMC-DATALAKE)
- [HYDRA-UMC-TELEMETRY-COLLECTOR](https://github.com/JuanenRac/HYDRA-UMC-TELEMETRY-COLLECTOR)
- [HYDRA-UMC-ANOMALY-DETECTOR](https://github.com/JuanenRac/HYDRA-UMC-ANOMALY-DETECTOR)
- [HYDRA-UMC-PRODUCTION-REPORTS](https://github.com/JuanenRac/HYDRA-UMC-PRODUCTION-REPORTS)

**🏭 Industrielles Gateway**
- [HYDRA-UMC-GATEWAY-INDUSTRIAL](https://github.com/JuanenRac/HYDRA-UMC-GATEWAY-INDUSTRIAL)
- [HYDRA-UMC-OPCUA-SERVER](https://github.com/JuanenRac/HYDRA-UMC-OPCUA-SERVER)
- [HYDRA-UMC-MQTT-BROKER](https://github.com/JuanenRac/HYDRA-UMC-MQTT-BROKER)
- [HYDRA-UMC-MTCONNECT-ADAPTER](https://github.com/JuanenRac/HYDRA-UMC-MTCONNECT-ADAPTER)

**🛠️ Ergänzende Werkzeuge**
- [URTC-SMART-RACK](https://github.com/JuanenRac/URTC-SMART-RACK)
- [URTC-VISION-TOOL](https://github.com/JuanenRac/URTC-VISION-TOOL)
- [HYDRA-UMC-WATCH](https://github.com/JuanenRac/HYDRA-UMC-WATCH)
- [HYDRA-UMC-TOOL-CLI](https://github.com/JuanenRac/HYDRA-UMC-TOOL-CLI)
- [HYDRA-UMC-DASHBOARD-AI](https://github.com/JuanenRac/HYDRA-UMC-DASHBOARD-AI)

---

## 👤 AUTOR
**JuanenRac** (Electro Hobby 3D)
📧 electrohobby3d@gmail.com
📺 [youtube.com/@electrohobby3d](https://youtube.com/@electrohobby3d)

## 📜 LIZENZ
GPL-3.0 - Siehe LICENSE-Datei für Details.
