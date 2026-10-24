<p align="center">
  <img src="images/HYDRA_UMC_BANNER.svg" alt="HYDRA-UMC-VISION-STREAMER banner" width="100%">
</p>

# 📹 HYDRA-UMC-VISION-STREAMER

<p align="center"><a href="README.md">🇺🇸 English</a> | <a href="README_spa.md">🇪🇸 Español</a> | <a href="README_fra.md">🇫🇷 Français</a> | <a href="README_ita.md">🇮🇹 Italiano</a> | 🇩🇪 <b>Deutsch</b> | <a href="README_zho.md">🇨🇳 简体中文</a> | <a href="README_jpn.md">🇯🇵 日本語</a> | <a href="README_por.md">🇵🇹 Português</a></p>

### 🚀 Optimierte GStreamer-Pipeline für Multi-Kamera-Edge-KI

<p align="center">
  <img src="https://img.shields.io/badge/Lizenz-GPL%203.0--or--later-blue.svg" alt="GPL 3.0 or later">
  <img src="https://img.shields.io/badge/Framework-GStreamer-62B417.svg" alt="GStreamer">
  <img src="https://img.shields.io/badge/Plattform-Raspberry%20Pi%20CM5-BC1142.svg" alt="CM5">
  <img src="https://img.shields.io/badge/Schnittstelle-8x%20USB%203.0-blue.svg" alt="8x USB 3.0">
  <img src="https://img.shields.io/badge/Stufe-Funktional%20v0-green.svg" alt="Funktional v0">
</p>

---

> **Stand von Sicherheit (Safety) und Security:** Dieses Ökosystem ist kein zertifiziertes Sicherheitssystem. Es gibt noch keinen Hardware-E-STOP-Pfad, keine von der Firmware durchgesetzten Grenzen oder Verriegelungen und keinen verifizierten Bewegungsbefehl; Firmware-Images werden mit CRC32 und einem HMAC-SHA256 mit gemeinsamem Schlüssel geprüft, nicht mit einer asymmetrischen Signatur; TLS und gegenseitiges TLS sind optional und standardmäßig aus; noch keine eigene Platine wurde bestückt oder getestet. Lesen Sie die [Sicherheitsbasis](https://github.com/JuanenRac/HYDRA-UMC-DOCS/blob/main/docs/SECURITY_BASELINE.md) und das [Bedrohungsmodell](https://github.com/JuanenRac/HYDRA-UMC-DOCS/blob/main/docs/THREAT_MODEL.md), bevor Sie sich für die Sicherheit einer Person auf eine Aussage hier verlassen.

## 📋 Auf einen Blick

| | |
|---|---|
| Version | `0.2.1` |
| Reifegrad | Etabliert |
| Tests | 109 |
| Technik | Python / GStreamer / MediaMTX |
| Ziel | Der Raspberry Pi CM5 einer HYDRA-UMC-Zelle |
| Auf echter Hardware | Noch nicht: für diese Version ist kein Lauf auf echter Hardware vermerkt |

## 🚦 Projektstatus

Jede Zeile ist ein Teil dieses Repositorys, und die Ampel sagt, wie weit er heute ist. Sie beruht auf dem, was das Repository zeigen kann (Tests, Builds, Läufe), nicht auf dem, was geplant ist.

🟢 Fertig und überprüft · 🟡 Funktioniert, mit bekannten Grenzen · 🟠 Teilweise fertig oder noch nicht überprüft · 🔴 Nicht gemacht oder funktioniert nicht

| Bereich | Stand | Was das hier bedeutet |
|---|---|---|
| Software | 🟢 | Für seinen Zweck vollständig und stabil; die Ehrlichkeitsprüfung oben nennt die bekannten Grenzen |
| Tests | 🟢 | 109 automatische Tests, bei jeder Änderung ausgeführt |
| Echte Hardware | 🔴 | Noch nicht: für diese Version ist kein Lauf auf echter Hardware vermerkt |
| Dokumentation | 🟢 | README in acht Sprachen, bei jeder Änderung gegen das Manifest geprüft |

## 1. 🛠️ TECHNISCHER ÜBERBLICK

**HYDRA-UMC-VISION-STREAMER** soll die leistungsstarke Medien-Erfassungsschicht der Vision-AI-Node-Familie werden. Seine Aufgabe ist die Erfassung auf niedriger Ebene, Vorverarbeitung und Verteilung von bis zu 8 gleichzeitigen USB-3.0-Kameraströmen, unter Nutzung des hardwarebeschleunigten ISP des Broadcom BCM2712 (CM5) für Farbraumkonvertierung, Skalierung und Normalisierung, bevor Frames die Hailo-8-NPU erreichen.

**Mehrere Betrachter, Zustand und Zugangsdaten:** Jeder Betrachter einer Kamera erhält jedes Bild (der gemeinsame Puffer wird nicht mehr vom ersten Leser verbraucht), `GET /health` antwortet mit `200`, solange Bilder ankommen, sonst mit `503` (`connecting`, `stalled`, `given_up`), und wenn alle Wiederverbindungsversuche verbraucht sind, beendet sich der Prozess jetzt mit einem Fehler, statt einen leeren Stream auszuliefern, sodass sein Supervisor ihn neu startet. Passwörter in RTSP-URLs werden in Logs und Meldungen maskiert; übergeben Sie die URL mit `--device-env VAR` (eine Umgebungsvariable) statt `--device`, damit sie nicht in der Prozessliste erscheint. Hosts, Geräte und RTSP-Pfade werden geprüft, bevor sie in eine erzeugte Pipeline geschrieben werden, und die Pipeline einer IP-Kamera nutzt `rtspsrc` mit begrenzten, verwerfenden Queues. Alles, was der Streamer protokolliert, läuft jetzt auch durch die gemeinsame Geheimnis-Schwärzung (Token, `password=`-Werte und Bearer-Header zusätzlich zu den URL-Zugangsdaten), dasselbe Modul und dieselben Testvektoren wie in den anderen Projekten.

Dies ist eines der 4 Kind-Projekte von **[HYDRA-UMC-VISION-NODE](https://github.com/JuanenRac/HYDRA-UMC-VISION-NODE)**, dem Integrations-Elternteil der Familie: Dieses Projekt besitzt nur Erfassung/Vorverarbeitung und führt weder eigene Hailo-8-Inferenz noch eine gRPC-API oder Sicherheitslogik aus - das ist bewusst auf seine 3 Geschwister verteilt.

### Kernpunkte

* 🔑 **Optionales Bearer-Token:** auf Loopback braucht der Stream kein Token; außerhalb von Loopback startet er ohne eines nicht (`--token-file` oder `HYDRA_UMC_VISION_STREAMER_TOKEN`). Ist ein Token gesetzt, muss `/stream` mit `Authorization: Bearer <token>` angefordert werden (Vergleich in konstanter Zeit); nur `GET /health` bleibt offen. *(implementiert)*
* ✅ **Echtes v0 - Config-, Pipeline- und Relay-Generierung:** `config.py` validiert eine JSON-Konfiguration pro Kamera (Gerät, Auflösung, fps, Format); `pipeline.py` generiert die exakte GStreamer-Pipeline-Beschreibung für eine Kamera; `mediamtx_config.py` generiert die passende MediaMTX-`paths.yml`. Über `config validate`/`config gst`/`config mediamtx` unten verfügbar - kein GStreamer-Laufzeitsystem, V4L2 oder physische Kamera nötig, um es auszuführen oder zu testen.
* 📷 **Echtes v0 - USB- und RTSP-IP-Kamera-Erfassung+Bereitstellung:** `mjpeg_server.py`s `stream serve` öffnet tatsächlich eine Kamera und liefert echtes MJPEG über HTTP - ein USB/V4L2-Gerät (`--device 0`) oder eine echte RTSP-IP-Kamera (`--device rtsp://user:pass@host:port/pfad`, über OpenCVs `cv2.CAP_FFMPEG`-Backend, keine zusätzliche Abhängigkeit). `config.py`s `CameraConfig` trägt jetzt einen echten `source_type` (`"usb"` als Standard, oder `"ip"` mit `host`/`rtsp_port`/`rtsp_path`/`username`/`password` und einem echten, percent-encodierten `rtsp_url()`-Builder). Ende-zu-Ende gegen echte Hardware verifiziert: alle 4 echten IP-Kameras im lokalen Netzwerk öffneten sich und übertrugen echte MJPEG/H.264-Frames über exakt diesen Pfad (das 2. Paar brauchte seinen eigenen echten RTSP-Pfad, `profile0`, gefunden auf dem eigenen Config-Bildschirm der Kamera - ein anderer Pfad als das `/11` des ersten Paars, kein Zugangsdaten- oder Firmware-Problem).
* 🔁 **Echtes v0 - Begrenzte Pufferung und Wiederverbindung:** `FrameBuffer` in `buffer.py` ist eine Warteschlange fester Kapazität, die beim Vollsein das ÄLTESTE Element verwirft (nie das neueste) - die echte Backpressure-Politik, die ein Live-Relay braucht, damit ein langsamer Konsument den Speicher dieses Prozesses niemals unbegrenzt wachsen lassen kann. `ConnectionTracker` in `reconnect.py` ist eine echte, deterministische Wiederverbindungspolitik mit exponentiellem Backoff für eine abgebrochene Kamera-/Relay-Verbindung. `mjpeg_server.py`'s eigener realer Erfassungspfad puffert einen `Frame` (nicht nur reine Bytes) - eine echte `frame_id`/`session_id`/`capture_ts`-Identität, mit einer wirklich neuen `session_id` bei jeder echten Wiederverbindung, sodass zwei Frames von vor/nach einer abgebrochenen Verbindung niemals als ein durchgehender Stream verwechselt werden. Über `stream simulate` unten verfügbar - vollständig testbar ohne GStreamer oder physische Kamera.
* 📡 **RTSP/WebRTC-Unterstützung (teilweise geplant):** der RTSP-Relay-Pfad (`rtspclientsink` → MediaMTX) ist entworfen und seine Konfiguration wird oben real generiert; ihn tatsächlich auszuführen benötigt das GStreamer-Laufzeitsystem, das diese Umgebung nicht hat. Die WebRTC-Ausgabe bleibt vollständig geplant.
* 🔌 **HailoRT-Integrationsgrenze, dem Modul vorausgehend vorbereitet:** `hailo_runtime.py` ist gegen die echte, bestätigte `hailo_platform`-API (`VDevice`, `HEF`, `ConfigureParams`) geschrieben - lazy importiert, sodass dieses Repository ohne installiertes `hailort`-Paket oder vorhandenes Hailo-8-Modul sauber installiert/getestet wird - plus eine echte Preflight-Validierung, dass die konfigurierte Auflösung einer Kamera tatsächlich mit der Eingabe-Tensor-Form eines geladenen Modells übereinstimmt, bevor auch nur ein einziges Frame an das Gerät gesendet wird. *(implementiert, nur Integrationsgrenze - tatsächliche Inferenz auszuführen und die echte NMS-Ausgabe eines Modells zu parsen ist weiterhin zukünftige Arbeit.)*
* ⚡ **Zero-Copy-Pipeline (geplant):** Buffer-Übergabe zwischen V4L2 und HailoRT, entworfen, um unnötige Frame-Kopien zu vermeiden. *(zukünftige Arbeit - benötigt das echte V4L2/HailoRT-Laufzeitsystem, das diese Umgebung nicht hat.)*
* 🌈 **Vorverarbeitung (geplant, Backend noch zu wählen):** Echtzeit-Skalierung und Pixelformatkonvertierung, die der CPU Arbeit pro Frame abnimmt. Der ISP der Pi 5 (PiSP) bedient Kameras am CSI-Anschluss über libcamera, nicht USB-Kameras; für USB-Kameras würde die Konvertierung auf der CPU oder in einem V4L2-Speicher-zu-Speicher-Block laufen, was noch weder untersucht noch gewählt ist. *(zukünftige Arbeit: braucht die echte V4L2-Laufzeit und eine Kamera, die diese Umgebung nicht hat.)*
* 🪪 **Bildidentität, letztes Bild und mehrere Kameras in einem Prozess:** Jeder Teil des MJPEG-Stroms trägt `X-Frame-Id`, `X-Session-Id` und `X-Capture-Ts` (Millisekunden seit der Epoche, genommen, als der Sensor das Bild lieferte), so dass ein Verbraucher das Alter eines Bildes bestimmen kann; `GET /latest.jpg` und `GET /latest.json` antworten das neueste Bild samt Identität und Alter, ohne einen Strom offen zu halten. `stream serve --config cams.json --camera NAME` nimmt Gerät, Größe und Rate (und die RTSP-Zugangsdaten einer IP-Kamera) aus der Liste, so dass weder eine Unit-Datei noch die Prozessliste sie trägt, und `stream serve-all --config cams.json --port N` bedient alle Kameras der Liste aus einem Prozess und einem Port (`/<name>/stream`, `/<name>/latest.jpg`, `/<name>/latest.json`, `/<name>/health`, `/health`) statt aus einem Interpreter und einer OpenCV-Kopie pro Kamera. *(mit simulierten Quellen getestet; nicht mit echten Kameras)*
* 🛠️ **Dynamische Konfiguration:** Auflösung, Framerate und Pixelformat pro Kamera sind heute real und werden validiert (`config.py`); die Belichtungs-/Verstärkungssteuerung benötigt das echte V4L2-Gerät und ist zukünftige Arbeit.
* 🧩 **Warum als eigenes Projekt:** Erfassungs-/ISP-Abstimmung ist eine andere Fähigkeit und eine andere Fehlerdomäne als Modellinferenz oder Sicherheitslogik - sie im eigenen Prozess zu halten bedeutet, dass ein Erfassungsfehler [HYDRA-UMC-SAFETY-ZONES](https://github.com/JuanenRac/HYDRA-UMC-SAFETY-ZONES) nicht lahmlegen kann, und beide können unabhängig entwickelt/getestet werden.

**Ehrlichkeitscheck - was heute wirklich läuft:** die Konfigurationsvalidierung, die Generierung der GStreamer-Pipeline-Beschreibung, die Generierung der MediaMTX-Relay-Konfiguration, und die echte Puffer-/Wiederverbindungspolitik, und eine echte HailoRT-Integrationsgrenze (`config.py`, `pipeline.py`, `mediamtx_config.py`, `buffer.py`, `reconnect.py`, `hailo_runtime.py`) sind real und getestet (105 Tests). Nichts davon öffnet ein V4L2-Gerät, importiert GStreamer oder spricht mit einer physischen Kamera - die generierte Pipeline tatsächlich auszuführen benötigt dieses echte Laufzeitsystem und diese echte Hardware, die diese Umgebung nicht hat. Siehe [`CHANGELOG.md`](CHANGELOG.md) für genau das, was bisher geliefert wurde, und "Aktueller Status & Nächste Schritte" unten für das, was noch offen ist. `/stream` begrenzt gleichzeitige Zuschauer mit `--max-clients` (Standard 5, darüber ein echtes 503), um die begrenzte WLAN-Anbindung eines CM5 zu schützen, und trennt einen Zuschauer, der nach 30 Sekunden aufhört zu lesen (ein Socket-Timeout), sodass ein festhängender Client nie dauerhaft einen der Plätze belegt.

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
│       ├── __init__.py          # Paketbeschreibung und Version
│       ├── config.py           # Parsen/Validierung der Konfiguration pro Kamera
│       ├── pipeline.py         # Generierung der GStreamer-Pipeline-Beschreibung
│       ├── mediamtx_config.py  # Generierung der MediaMTX-paths.yml
│       ├── buffer.py           # Echter begrenzter Puffer (drop-oldest Backpressure)
│       ├── reconnect.py        # Echte deterministische Wiederverbindungs-/Backoff-Politik
│       ├── hailo_runtime.py    # Echte HailoRT-Integrationsgrenze (hailo_platform), lazy importiert
│       ├── mjpeg_server.py     # Echter MJPEG-Server - liefert tatsächlich das Bild einer USB-Webcam oder einer RTSP-IP-Kamera per HTTP
│       ├── access.py           # Optionales Bearer-Token für die HTTP-API (auf Loopback nicht nötig, sonst Pflicht)
│       ├── log_redaction.py    # Gemeinsame Schwärzung von Geheimnissen in Text und JSON-artigen Werten (Kopie des kanonischen SDK-Moduls)
│       └── main.py             # CLI-Einstiegspunkt (nackter Aufruf + `config`/`stream`)
├── tests/               # Echte pytest-Suite (config, pipeline, mediamtx, buffer, reconnect, hailo_runtime, mjpeg_server, CLI)
├── docs/                # Dokumentation und Tuning-Anleitungen
├── build/               # Build-Ausgabe (das lokale .venv liegt im Wurzelverzeichnis des Repositorys)
├── images/              # Medien und Diagramme
├── systemd/
│   ├── hydra-umc-vision-streamer@.service  # Pro Kamera instanziierte systemd-Unit
│   └── cameras.env.example                 # Beispiel-Umgebungsdatei pro Instanz
├── tools/
│   ├── build_test.py    # Nicht-versionierender Build-Check
│   ├── ci_validate.py   # Manifest/CHANGELOG/Docs-Validierung, von CI genutzt
│   ├── _doc_policy.py   # Von der Familie geteilte Dokumentationsregeln (Kopie der von HYDRA-UMC-SDK, synchron gehalten)
│   ├── _readme_parity.py # Prüfung, dass die acht READMEs dieselbe Struktur haben (Kopie der von HYDRA-UMC-SDK, synchron gehalten)
│   ├── hydra_project_tool.py # Dieselben Befehle in jedem Repository: validate, test, ci, version, status, bump
│   └── extra_build_steps.py # Die eigenen Build-Schritte dieses Repositorys neben dem gemeinsamen Build-Test (seine Unit-Tests)
├── pyproject.toml       # Paketmetadaten, Abhängigkeiten, Kilometerzähler-Version
├── bump_version.py      # Versionserhöhung im Kilometerzähler-Stil (nur vom expliziten `bump`-Befehl ausgeführt)
├── bump_manifest_version.py # Synchronisiert die Version von hydra-umc.project.json mit der nativen (--sync)
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

1. **Versionsprüfung** - liest und zeigt die Projektversion an; Bauen ändert sie nie (nur `python tools/hydra_project_tool.py bump` erhöht sie).
2. **Virtuelle Umgebung** - erstellt `.venv/`, falls nicht vorhanden; verwendet es sonst weiter.
3. **Editierbare Installation** - `pip install -e ".[dev]"`, sodass Änderungen unter `src/` sofort wirken, installiert `pytest`, und registriert den Konsolen-Einstiegspunkt `hydra-umc-vision-streamer`.
4. **Compile-Check** - `python -m compileall -q src` kompiliert jede Datei unter `src/` zu Bytecode und findet so Syntaxfehler im gesamten Paket.
5. **Echte Test-Suite** - `python -m pytest tests/ -q` (105 Tests, die config, pipeline, MediaMTX-Generierung, die Puffer-/Wiederverbindungspolitik, die HailoRT-Integrationsgrenze und die CLI abdecken).

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

Echtes Beispiel - erfasst+liefert tatsächlich eine Kamera als MJPEG über HTTP (der einzige Unterbefehl, der ein echtes Gerät öffnet):

```bash
# USB/V4L2-Gerät
./run.sh stream serve --device 0 --port 8100

# Echte RTSP-IP-Kamera (gegen echte Hardware verifiziert - siehe CHANGELOG.md)
CAMERA_URL="rtsp://admin:secret@192.168.0.211:554/11" ./run.sh stream serve --device-env CAMERA_URL --port 8100 --width 1920 --height 1080 --fps 15
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

**Was heute funktioniert:** die Konfigurationsvalidierung, die Generierung der GStreamer-Pipeline-Beschreibung, und die Generierung der MediaMTX-Relay-Konfiguration (`config.py`, `pipeline.py`, `mediamtx_config.py`), ein echter, nachweislich begrenzter Puffer und eine echte deterministische Wiederverbindungspolitik (`buffer.py`, `reconnect.py`, `stream simulate`), eine echte HailoRT-Integrationsgrenze (`hailo_runtime.py`), bereit für ein echtes Hailo-8-Modul, sobald es angeschlossen wird, und ein echter v0-Capture+Serve-Pfad (`mjpeg_server.py`, `stream serve`), der ein echtes USB/V4L2-Gerät **oder eine echte RTSP-IP-Kamera** (`source_type: "ip"` in `config.py`, `cv2.CAP_FFMPEG` in `mjpeg_server.py`) über OpenCV öffnet und echtes MJPEG über HTTP ausliefert - installierbar auf einer CM5 über `provisioning/install_vision_streamer.sh` von `HYDRA-UMC-OS` (eine systemd-Instanz pro vom Administrator zugewiesenem Kamera-Slot, `systemd/hydra-umc-vision-streamer@.service`) und bereits live genutzt vom `GET /api/camera/:id/stream`-Proxy von `HYDRA-UMC-SERVER` und den Kameraansichten von `HYDRA-UMC-STUDIO`. Der IP-Kamera-Pfad ist Ende-zu-Ende gegen echte Hardware verifiziert: alle 4 echten IP-Kameras im lokalen Netzwerk öffneten sich und übertrugen echte Frames über den vollständigen echten Pfad - 105 Tests insgesamt, plus ein echtes, installierbares Python-Paket mit verifiziertem Einstiegspunkt und ein expliziter `bump`-Befehl im Kilometerzähler-Stil, der die Version erhöht (der Build ändert sie nie). Siehe [`CHANGELOG.md`](CHANGELOG.md) für die erfasste Build-/Run-Ausgabe.

**Was noch offen ist, ohne bestimmte Reihenfolge, ohne verbindlichen Zeitplan, und blockiert durch echte Hardware:**

* Die *generierte Pipeline* tatsächlich auszuführen - der vollständige GStreamer/PyGObject-Tee in einen Hailo-8-Inferenzzweig, nicht das einfachere OpenCV-v0 (`stream serve` oben) - über ein echtes Laufzeitsystem.
* Hardware-Vorverarbeitung (Skalierung/Formatkonvertierung): Der ISP der Pi 5 bedient keine USB-Kameras, daher muss zuerst das Backend gewählt werden.
* Die Inferenz tatsächlich über `hailo_runtime.py` auszuführen (benötigt ein echtes Hailo-8-Modul und eine echte kompilierte `.hef`), und das reale NMS-Ausgabeformat dieses Modells zu parsen - bewusst nicht ohne das Gerät zur Verifikation geraten.
* WebRTC-Ausgabe, und Belichtungs-/Verstärkungssteuerung pro Kamera (benötigt das echte V4L2-Gerät).
* `stream serve` wurde noch nicht gegen eine real angeschlossene USB-Kamera verifiziert - nur gegen ein an der Modulgrenze gemocktes `cv2.VideoCapture` (siehe `tests/test_mjpeg_server.py`).

---

## 🔗 Verwandte Projekte

Dieses Projekt ist Teil des HYDRA-UMC-Robotik-Ökosystems desselben Autors (JuanenRac / Electro Hobby 3D). Gut zu wissen, da eine Anfrage eigentlich eines dieser Projekte betreffen könnte statt dieses Repositorys.

**Übergeordnetes Projekt**
- **[HYDRA-UMC-VISION-NODE](https://github.com/JuanenRac/HYDRA-UMC-VISION-NODE)** — Integrationsknoten für die Hailo-8-Vision-Pipeline, mit einer echten stufenweisen Hardware-Bereitschaftsprüfung; das übergeordnete Projekt, dessen spezifische Stufe bzw. Verbraucher dieses Repository innerhalb seiner eigenen Wahrnehmungs-Pipeline ist.

**Geschwisterprojekte** — die übrigen Stufen/Verbraucher der eigenen Hailo-8-Wahrnehmungs-Pipeline von HYDRA-UMC-VISION-NODE
- **[HYDRA-UMC-DETECTION-HEF](https://github.com/JuanenRac/HYDRA-UMC-DETECTION-HEF)** — echte Registry für kompilierte Modelle mit Hailo-Architektur-/Prüfsummen-Safe-Load-Verifizierung.
- **[HYDRA-UMC-SAFETY-ZONES](https://github.com/JuanenRac/HYDRA-UMC-SAFETY-ZONES)** — v0-Logik für Zonenverletzung, Kalibrierungsaktualität und E-STOP-Anforderung, die Objektpositionen aus einer Datei nimmt; kein Detektor speist sie, und noch kein physischer E-STOP ist angeschlossen.
- **[HYDRA-UMC-VISUAL-SERVOING-API](https://github.com/JuanenRac/HYDRA-UMC-VISUAL-SERVOING-API)** — Position-Based-Visual-Servoing-Korrekturgesetz mit Freigabe abhängig vom Zonenstatus; noch keine Posenschätzung per Kamera.

**Ebenfalls Teil des Ökosystems**

*Kern-Hardware & Plattform*
- **[HYDRA-UMC](https://github.com/JuanenRac/HYDRA-UMC)** — der Entwurf des Motherboards des Roboterarms: CM5-Host + Dual-Core-STM32H745, gedacht zur Koordination von bis zu 8 Werkzeugarmen über CAN-OTA/SPI-OTA (Firmware in einer frühen Phase; noch keine bestückte Platine).
- **[HYDRA-UMC-OS](https://github.com/JuanenRac/HYDRA-UMC-OS)** — reproduzierbare Raspberry-Pi-OS-Produktschicht für den CM5: schreibgeschützter Agent, validierte Konfiguration/Profile, WiFi-Ersteinrichtung.
- **[HYDRA-UMC-SDK](https://github.com/JuanenRac/HYDRA-UMC-SDK)** — der gemeinsame JSON-Schema-Vertrag und die Software-Auftragsschranke, gegen die jede Bridge ihre Befehle validiert (keine zertifizierte Sicherheitsfunktion).
- **[HYDRA-UMC-CONNECTOR-HUB](https://github.com/JuanenRac/HYDRA-UMC-CONNECTOR-HUB)** — deklaratives Adapter-Manifest-Register und Validator für Konnektoren externer Maschinen; erweitert die eigene Vertragsidee des SDK auf externe Maschinen, ohne die Industrie-Gateway-Projekte zu ersetzen.

*Kern-Backend & Clients*
- **[HYDRA-UMC-SERVER](https://github.com/JuanenRac/HYDRA-UMC-SERVER)** — das reale Headless-Backend (REST/WebSocket), mit dem jeder Steuerungsclient tatsächlich spricht.
- **[HYDRA-UMC-STUDIO](https://github.com/JuanenRac/HYDRA-UMC-STUDIO)** — Web-Steuerungs-Dashboard mit Echtzeit-3D-Visualisierung mehrerer Roboter.
- **[HYDRA-UMC-SUITE](https://github.com/JuanenRac/HYDRA-UMC-SUITE)** — Desktop-Schwarmleitstand (PySide6) für mehrere Server gleichzeitig, verpackt als eigenständige ausführbare Datei.
- **[HYDRA-UMC-ANDROID-CONTROL](https://github.com/JuanenRac/HYDRA-UMC-ANDROID-CONTROL)** — native Android-Steuerungs-App mit biometrischem Login und einer gekoppelten Wear-OS-Begleit-App.
- **[HYDRA-UMC-IOS-CONTROL](https://github.com/JuanenRac/HYDRA-UMC-IOS-CONTROL)** — iOS/iPadOS-Steuerungs-App (Flutter) mit Echtzeit-WebSocket-Synchronisierung.
- **[HYDRA-UMC-DSI](https://github.com/JuanenRac/HYDRA-UMC-DSI)** — native Touch-UI für das eingebaute 7"-DSI-Touchscreen, direkt auf dem CM5 eingebettet.
- **[HYDRA-UMC-EDITOR-URDF](https://github.com/JuanenRac/HYDRA-UMC-EDITOR-URDF)** — grafischer Desktop-URDF-Ersteller/-Editor, der fertige Modelle in STUDIOs eigenen Katalog überträgt.
- **[HYDRA-UMC-EDITOR-STL](https://github.com/JuanenRac/HYDRA-UMC-EDITOR-STL)** — Desktop-STL-Modelleditor, der echte Teile im selben Modellkatalog transformiert/ersetzt/entfernt/hinzufügt, den auch HYDRA-UMC-EDITOR-URDF bearbeitet.
- **[HYDRA-UMC-BRIDGE-AMR](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-AMR)** — Koordinationsschranke für AGV-/AMR-Flotten über einen VDA-5050-MQTT-Publisher (nur gegen eine emulierte Flotte getestet).
- **[HYDRA-UMC-BRIDGE-CNC](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-CNC)** — High-Level-Koordinator für CNC-Zellen mit GRBL-Status-/Steuerbyte-Zugriff (nur gegen einen Emulator getestet).
- **[HYDRA-UMC-BRIDGE-DROIDS](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-DROIDS)** — Koordinationsschranke für laufende/humanoide Droiden, mit einem Boston-Dynamics-Spot-Befehlssender (nur gegen einen Emulator getestet).
- **[HYDRA-UMC-BRIDGE-LASER](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-LASER)** — Koordinator für Laserzellen, liest 3 Schlüssel-/Gehäuse-/Verriegelungs-GPIO-Signale (nur gegen einen simulierten Chip getestet; kann keinen Laser scharfschalten oder auslösen).
- **[HYDRA-UMC-BRIDGE-OPENPNP](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-OPENPNP)** — sicherer High-Level-Koordinator für den Leiterplattenfluss von OpenPnP Pick-and-Place.
- **[HYDRA-UMC-BRIDGE-PRINTER3D](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-PRINTER3D)** — sichere Koordinationsschranke für Moonraker/Klipper-3D-Drucker, mit echten gesicherten Job-Befehlen.
- **[HYDRA-UMC-BRIDGE-ROS2](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-ROS2)** — Koordinator mit einem träge importierten rclpy-ROS-2-Transport (noch nicht gegen eine ROS-2-Installation ausgeführt).
- **[HYDRA-UMC-BRIDGE-UAV](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-UAV)** — Koordinationsschranke für kameraausgestattete UAVs, mit einem MAVLink-Befehlssender (nur gegen einen Emulator getestet).

*URTC-Werkzeugplattform*
- **[URTC](https://github.com/JuanenRac/URTC)** — Firmware für die physische Universal-Robot-Tool-Controller-Platine, 25+ Werkzeugprofile über CAN-Bus.
- **[URTC-FLASHER](https://github.com/JuanenRac/URTC-FLASHER)** — Desktop-GUI-Flash-Tool für URTC-Platinen, CAN-OTA plus Full-Chip-SWD/JTAG.
- **[URTC-TESTER](https://github.com/JuanenRac/URTC-TESTER)** — Desktop-Live-CAN-Bus-Diagnosetool für URTC-Platinen, ein Panel pro Werkzeugprofil.
- **[URTC-WEB-STUDIO](https://github.com/JuanenRac/URTC-WEB-STUDIO)** — browserbasierte Alternative zu URTC-TESTER über die Web-Serial-API, ohne lokale Installation.
- **[URTC-GATEWAY](https://github.com/JuanenRac/URTC-GATEWAY)** — Gateway vor dem CAN-Bus von URTC: Liste erlaubter Kennungen, Ratenbegrenzung und Sitzungsschlüssel; Software auf dem Computer getestet, noch nicht an einem echten Bus.

*Kognitiver KI-Knoten (Hailo-10)*
- **[HYDRA-UMC-COGNITIVE-NODE](https://github.com/JuanenRac/HYDRA-UMC-COGNITIVE-NODE)** — Integrationsknoten für die Hailo-10-Cognitive-Pipeline (LLM-/VLA-/Sprach-Orchestrierung).
- **[HYDRA-UMC-VLA-ENGINE](https://github.com/JuanenRac/HYDRA-UMC-VLA-ENGINE)** — echte Aktions-Token-Kodierung/-Dekodierung und Trajektoriengenerierung für ein Vision-Language-Action-Modell.
- **[HYDRA-UMC-VOICE-UI](https://github.com/JuanenRac/HYDRA-UMC-VOICE-UI)** — echtes Sprach-Frontend (VAD + Intent-Parser) mit einem begrenzten, bestätigungsgesicherten Watch-Relay.
- **[HYDRA-UMC-SEMANTIC-PLANNER](https://github.com/JuanenRac/HYDRA-UMC-SEMANTIC-PLANNER)** — echte regelbasierte Aufgabenzerlegung und semantische Fehlerbehebung über MCU-Fehlercodes.
- **[HYDRA-UMC-DOCS-QA](https://github.com/JuanenRac/HYDRA-UMC-DOCS-QA)** — echte, nur auf der Standardbibliothek basierende TF-IDF-Dokumentensuche über die eigenen Markdown-Dokumente dieses Ökosystems.
- **[HYDRA-UMC-LOCAL-TECHNICIAN](https://github.com/JuanenRac/HYDRA-UMC-LOCAL-TECHNICIAN)** — lokaler, richtlinien-gesteuerter KI-Wartungstechniker für das Ökosystem selbst - beobachtet, diagnostiziert und schlägt Korrekturen vor; die zwei höchsten Risikostufen sind absichtlich noch nicht implementiert.

*Orchestrierung & Schwarm*
- **[HYDRA-UMC-ORCHESTRATOR](https://github.com/JuanenRac/HYDRA-UMC-ORCHESTRATOR)** — Integrationsknoten mit einem echten gRPC/Protobuf-Health-Report-Vertrag und einer Missions-Zustandsmaschine.
- **[HYDRA-UMC-JOB-DISPATCHER](https://github.com/JuanenRac/HYDRA-UMC-JOB-DISPATCHER)** — echte prioritätsbasierte Job-Queue mit Deduplizierung, über eine echte HTTP-API.
- **[HYDRA-UMC-NODE-HEALING](https://github.com/JuanenRac/HYDRA-UMC-NODE-HEALING)** — echter gRPC-basierter Flotten-Health-Watchdog mit Retry/Backoff und Identitäts-Mismatch-Erkennung.
- **[HYDRA-UMC-PATH-PLANNER-3D](https://github.com/JuanenRac/HYDRA-UMC-PATH-PLANNER-3D)** — echter RRT-basierter 3D-Pfadplaner mit echter Hindernis-/Arbeitsraum-Kollisionsvalidierung.
- **[HYDRA-UMC-SWARM-SYNC](https://github.com/JuanenRac/HYDRA-UMC-SWARM-SYNC)** — echte CRDT-LWW-Element-Map-Zustandssynchronisation, eigenschaftsgetestet auf Multi-Zellen-Konvergenz.

*Digitaler Zwilling & Simulation*
- **[HYDRA-UMC-TWIN](https://github.com/JuanenRac/HYDRA-UMC-TWIN)** — Integrationsknoten für die Digital-Twin-Engine, mit einem echten Versionskompatibilitäts-Sync-Vertrag.
- **[HYDRA-UMC-HIL-BRIDGE](https://github.com/JuanenRac/HYDRA-UMC-HIL-BRIDGE)** — Hardware-in-the-Loop-Router mit einer Software-Kollisionsverriegelung zwischen Simulation und echter Hardware (ohne echte Hardware getestet).
- **[HYDRA-UMC-PHYSICS-REPLICA](https://github.com/JuanenRac/HYDRA-UMC-PHYSICS-REPLICA)** — echte Vorwärtskinematik und Gelenkgrenzenvalidierung über eine echte URDF-Teilmenge.
- **[HYDRA-UMC-SYNTHETIC-DATA-GEN](https://github.com/JuanenRac/HYDRA-UMC-SYNTHETIC-DATA-GEN)** — echter prozeduraler 2D-Szenengenerator mit YOLO/COCO-Annotationsexport.

*Daten & Analytik*
- **[HYDRA-UMC-DATALAKE](https://github.com/JuanenRac/HYDRA-UMC-DATALAKE)** — echter sqlite3-gestützter Zeitreihenspeicher mit einer echten Ingest-/Abfrage-HTTP-API.
- **[HYDRA-UMC-ANOMALY-DETECTOR](https://github.com/JuanenRac/HYDRA-UMC-ANOMALY-DETECTOR)** — echter FFT- + statistischer Basislinien-Anomaliedetektor mit Drift-Überwachung.
- **[HYDRA-UMC-PRODUCTION-REPORTS](https://github.com/JuanenRac/HYDRA-UMC-PRODUCTION-REPORTS)** — echte OEE-/Verfügbarkeitsberechnung über den DATALAKE-Verlauf, mit reproduzierbarem CSV-Export.
- **[HYDRA-UMC-TELEMETRY-COLLECTOR](https://github.com/JuanenRac/HYDRA-UMC-TELEMETRY-COLLECTOR)** — echte CAN/WebSocket-Ingestion-Pipeline in DATALAKE, mit Sequenz-Deduplizierung.

*Industrie-Gateway*
- **[HYDRA-UMC-GATEWAY-INDUSTRIAL](https://github.com/JuanenRac/HYDRA-UMC-GATEWAY-INDUSTRIAL)** — Integrationsknoten, der zu Industrieprotokollen weiterleitet, mit einer echten Befehls-Allowlist-/Backpressure-Schicht.
- **[HYDRA-UMC-OPCUA-SERVER](https://github.com/JuanenRac/HYDRA-UMC-OPCUA-SERVER)** — echter OPC-UA-Adressraum, verifiziert mit einer echten Binärprotokoll-Client-Session.
- **[HYDRA-UMC-MQTT-BROKER](https://github.com/JuanenRac/HYDRA-UMC-MQTT-BROKER)** — echter MQTT-Broker mit optionaler Pro-Client-Authentifizierung und Topic-ACLs.
- **[HYDRA-UMC-MTCONNECT-ADAPTER](https://github.com/JuanenRac/HYDRA-UMC-MTCONNECT-ADAPTER)** — echte MTConnect-`/probe`- und `/current`-XML-Endpunkte mit Degraded-Mode-Ausgabe.

*Ergänzende Tools & Ökosystembetrieb*
- **[HYDRA-UMC-DASHBOARD-AI](https://github.com/JuanenRac/HYDRA-UMC-DASHBOARD-AI)** — Smart-Summaries- und Anomaly-Highlighting-Panels über DATALAKE/ANOMALY-DETECTOR, mit einem ehrlichen statistischen Fallback.
- **[HYDRA-UMC-TOOL-CLI](https://github.com/JuanenRac/HYDRA-UMC-TOOL-CLI)** — Flotten-CLI mit einem echten, stabilen Exit-Code-Vertrag, ein echter Live-Client der eigenen API von HYDRA-UMC-SERVER.
- **[HYDRA-UMC-WATCH](https://github.com/JuanenRac/HYDRA-UMC-WATCH)** — WearOS-Begleit-App mit haptischen Alarmmustern und einem Sprach-Relay zum gekoppelten Telefon (noch nicht auf einer physischen Uhr ausgeführt).
- **[URTC-SMART-RACK](https://github.com/JuanenRac/URTC-SMART-RACK)** — Firmware für ein Platinenmontagegestell mit echter Werkzeug-ID-Dekodierung und Smart-Idle-Vorheizlogik.
- **[URTC-VISION-TOOL](https://github.com/JuanenRac/URTC-VISION-TOOL)** — Firmware plus ein echter Python-Vision-Begleiter für einen Thermal-/RGB-Inspektionswerkzeugkopf.
- **[HYDRA-UMC-UPDATER](https://github.com/JuanenRac/HYDRA-UMC-UPDATER)** — administratives Desktop-Tool, das jedes Repository in diesem Ökosystem entdeckt, klont und aktualisiert.
- **[HYDRA-UMC-OS-REBUILDER](https://github.com/JuanenRac/HYDRA-UMC-OS-REBUILDER)** — Windows/Linux-Desktop-Tool, das ein flashbereites CM5-Image baut, vorgeladen mit den aktuellsten Versionen des Ökosystems, mit Ersteinrichtungs-Konfiguration für WLAN/Benutzer/SSH im Stil von Raspberry Pi Imager.
- **[HYDRA-UMC-OPS-AGENT](https://github.com/JuanenRac/HYDRA-UMC-OPS-AGENT)** — Wartungsvorfall-Koordinator: eine Edge-Rolle mit niedrigem Privileg sammelt einen bereinigten Inventar-/Gesundheits-Snapshot, eine Control-Plane-Rolle rendert ihn schreibgeschützt und bittet einen KI-Anbieter um einen Diagnosevorschlag - wendet nie einen Patch an und stellt nie etwas bereit.
- **[HYDRA-UMC-DEV-SERVER](https://github.com/JuanenRac/HYDRA-UMC-DEV-SERVER)** — reproduzierbarer Entwicklungshost (Raspberry Pi 5 / CM5), der den Quellcode des Ökosystems vorhält und begrenzte Build-/Test-Aufgaben über eine dauerhafte Warteschlange ausführt; eine dedizierte Entwicklerrolle, ausdrücklich kein operativer CM5.

---

## 📚 Dokumentation & Community

- **[docs/CLI_REFERENCE.md](docs/CLI_REFERENCE.md)** — jeder Unterbefehl (`config validate`/`gst`/`mediamtx`, `stream simulate`/`serve`, einschließlich echter USB- und RTSP-IP-Kamera-Beispiele), mit echter erfasster Ausgabe.
- **[CONTRIBUTING.md](CONTRIBUTING.md)** — Technologie-Stack und Coding-Richtlinien für einen Pull Request.
- **[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)** — die in dieser Community erwarteten Verhaltensstandards.
- **[SECURITY.md](SECURITY.md)** — wie man eine Schwachstelle meldet, und die echten Sicherheitsschwerpunkte dieses Projekts.
- **[SUPPORT.md](SUPPORT.md)** — wo man Fragen stellt und Fehler meldet.
- **[LICENSE.md](LICENSE.md)** — die eigene Lizenz dieses Projekts.

## 👤 AUTOR
**JuanenRac** (Electro Hobby 3D)
📧 electrohobby3d@gmail.com
📺 [youtube.com/@electrohobby3d](https://youtube.com/@electrohobby3d)

## 📜 LIZENZ
GPL-3.0-or-later - Siehe LICENSE-Datei für Details.
