<p align="center">
  <img src="images/HYDRA_UMC_BANNER.svg" alt="HYDRA-UMC-VISION-STREAMER banner" width="100%">
</p>

# 📹 HYDRA-UMC-VISION-STREAMER

<p align="center"><a href="README.md">🇺🇸 English</a> | <a href="README_spa.md">🇪🇸 Español</a> | <a href="README_fra.md">🇫🇷 Français</a> | <a href="README_ita.md">🇮🇹 Italiano</a> | <a href="README_deu.md">🇩🇪 Deutsch</a> | <a href="README_zho.md">🇨🇳 简体中文</a> | <a href="README_jpn.md">🇯🇵 日本語</a> | 🇵🇹 <b>Português</b></p>

### 🚀 Pipeline GStreamer otimizado para IA de periferia com várias câmaras

<p align="center">
  <img src="https://img.shields.io/badge/License-GPL%203.0--or--later-blue.svg" alt="GPL 3.0 or later">
  <img src="https://img.shields.io/badge/Framework-GStreamer-62B417.svg" alt="GStreamer">
  <img src="https://img.shields.io/badge/Platform-Raspberry%20Pi%20CM5-BC1142.svg" alt="CM5">
  <img src="https://img.shields.io/badge/Interface-8x%20USB%203.0-blue.svg" alt="8x USB 3.0">
  <img src="https://img.shields.io/badge/Stage-Functional%20v0-green.svg" alt="Functional v0">
</p>

---

> **Estado de segurança (safety e security):** este ecossistema não é um sistema de segurança certificado. Ainda não existe um caminho de E-STOP por hardware, nem limites ou interlocks impostos pelo firmware, nem um comando de movimento verificado; as imagens de firmware são verificadas com CRC32 e um HMAC-SHA256 de chave partilhada, não com uma assinatura assimétrica; TLS e TLS mútuo são opcionais e estão desativados por defeito; nenhuma placa própria foi ainda montada ou testada. Leia a [base de segurança](https://github.com/JuanenRac/HYDRA-UMC-DOCS/blob/main/docs/SECURITY_BASELINE.md) e o [modelo de ameaças](https://github.com/JuanenRac/HYDRA-UMC-DOCS/blob/main/docs/THREAT_MODEL.md) antes de confiar em qualquer afirmação aqui para a segurança de uma pessoa.

## 📋 Num relance

| | |
|---|---|
| Versão | `0.2.0` |
| Maturidade | Estabelecido |
| Testes | 105 |
| Tecnologia | Python / GStreamer / MediaMTX |
| Destino | O Raspberry Pi CM5 de uma célula HYDRA-UMC |
| Em hardware real | Executado numa bancada de ensaio: a verificação de honestidade acima diz que partes correram em hardware real |

## 1. 🛠️ VISÃO TÉCNICA GERAL

O **HYDRA-UMC-VISION-STREAMER** destina-se a ser a camada de ingestão de multimédia de alto desempenho da família do Nó de IA de Visão. O seu trabalho é a captura de baixo nível, o pré-processamento e a distribuição de até 8 fluxos simultâneos de câmaras USB 3.0, usando o ISP acelerado por hardware do Broadcom BCM2712 (CM5) para fazer a conversão de espaço de cor, o redimensionamento e a normalização antes de as tramas chegarem à NPU Hailo-8.

É um dos 4 filhos do **[HYDRA-UMC-VISION-NODE](https://github.com/JuanenRac/HYDRA-UMC-VISION-NODE)**, o pai de integração da família: este projeto é dono apenas da captura/pré-processamento, e não executa a sua própria inferência Hailo-8, API gRPC nem lógica de segurança - isso está deliberadamente repartido pelos seus 3 irmãos.

### Pontos principais

* ✅ **Real v0 - geração de configuração, pipeline e relé:** o `config.py` valida uma configuração JSON por câmara (dispositivo, resolução, fps, formato); o `pipeline.py` gera a descrição exata do pipeline GStreamer de uma câmara; o `mediamtx_config.py` gera o `paths.yml` correspondente do MediaMTX. Exposto através de `config validate`/`config gst`/`config mediamtx` abaixo - não precisa de ambiente de execução GStreamer, de V4L2 nem de uma câmara física para executar ou testar nada disto.
* 📷 **Real v0 - captura e serviço de câmaras USB e IP RTSP:** o `stream serve` do `mjpeg_server.py` abre de facto uma câmara e serve MJPEG real por HTTP - um dispositivo USB/V4L2 (`--device 0`) ou uma câmara IP RTSP real (`--device rtsp://user:pass@host:port/path`, através do backend `cv2.CAP_FFMPEG` do OpenCV, sem dependência extra). O `CameraConfig` do `config.py` leva agora um `source_type` real (`"usb"` por omissão, ou `"ip"` com `host`/`rtsp_port`/`rtsp_path`/`username`/`password` e um construtor real de `rtsp_url()` com codificação percentual). Verificado de ponta a ponta contra hardware real: as 4 câmaras IP reais da rede local abriram e transmitiram tramas MJPEG/H.264 reais por este mesmo caminho (o 2.º par precisava do seu próprio caminho RTSP real, `profile0`, encontrado no ecrã de configuração da própria câmara - um caminho diferente do `/11` do primeiro par, não um problema de credenciais nem de firmware).
* 🔁 **Real v0 - memória intermédia limitada e religação:** o `FrameBuffer` do `buffer.py` é uma fila de capacidade fixa que descarta a trama MAIS ANTIGA (nunca a mais recente) quando fica cheia - a política real de contrapressão de que um relé em direto precisa para que um consumidor lento nunca faça a memória deste processo crescer sem limite. O `ConnectionTracker` do `reconnect.py` é uma política real e determinística de religação com recuo exponencial para uma ligação de câmara/relé caída. O próprio caminho real de captura do `mjpeg_server.py` guarda uma `Frame` (não apenas bytes soltos) - uma identidade real `frame_id`/`session_id`/`capture_ts`, com um `session_id` genuinamente novo em cada religação real, para que duas tramas de antes/depois de uma ligação caída nunca sejam confundidas com um único fluxo contínuo. Exposto através de `stream simulate` abaixo - totalmente testável sem GStreamer nem câmara física.
* 📡 **Suporte RTSP/WebRTC (parcialmente planeado):** o caminho de relé RTSP (`rtspclientsink` → MediaMTX) está desenhado e a sua configuração é gerada a sério acima; executá-lo a sério precisa do ambiente de execução GStreamer que este ambiente não tem. A saída WebRTC continua totalmente planeada.
* ⚡ **Pipeline sem cópias (planeado):** passagem de memórias intermédias entre V4L2 e HailoRT desenhada para evitar cópias desnecessárias de tramas. *(trabalho futuro - precisa do ambiente de execução V4L2/HailoRT real que este ambiente não tem.)*
* 🔌 **Fronteira de integração com o HailoRT, preparada antes do módulo:** o `hailo_runtime.py` está escrito contra a API real e confirmada do `hailo_platform` (`VDevice`, `HEF`, `ConfigureParams`) - importada sob demanda para que este repositório instale/teste de forma limpa sem o pacote `hailort` nem um módulo Hailo-8 - mais uma validação prévia real de que a resolução configurada de uma câmara corresponde de facto à forma do tensor de entrada de um modelo carregado, antes de uma única trama ser enviada ao dispositivo. *(implementado, apenas a fronteira de integração - executar inferência a sério e analisar a saída NMS de um modelo real continua a ser trabalho futuro.)*
* 🌈 **Pré-processamento por hardware (planeado):** redimensionamento em tempo real e conversão de formato de píxeis com o ISP do Pi, aliviando trabalho que o CPU teria de fazer por trama. *(trabalho futuro, pelo mesmo motivo.)*
* 🛠️ **Configuração dinâmica:** a resolução, a taxa de tramas e o formato de píxeis por câmara são reais e validados hoje (`config.py`); o controlo de exposição/ganho precisa do dispositivo V4L2 real e é trabalho futuro.
* 🧩 **Porque existe como projeto próprio:** a captura/afinação do ISP é uma competência diferente e um domínio de falhas diferente da inferência de modelos ou da lógica de segurança - mantê-la no seu próprio processo significa que um erro de captura não pode derrubar o [HYDRA-UMC-SAFETY-ZONES](https://github.com/JuanenRac/HYDRA-UMC-SAFETY-ZONES), e que os dois podem ser desenvolvidos/testados de forma independente.

**Verificação de honestidade - o que realmente funciona hoje:** a validação de configuração, a geração da descrição do pipeline GStreamer, a geração da configuração do relé MediaMTX, a política real de memória intermédia/religação e a fronteira de integração com o HailoRT (`config.py`, `pipeline.py`, `mediamtx_config.py`, `buffer.py`, `reconnect.py`, `hailo_runtime.py`) são reais e testadas (105 testes). O `stream serve` (`mjpeg_server.py`) é o único caminho que abre uma câmara real - um dispositivo USB/V4L2 ou uma câmara IP RTSP real - e foi verificado contra câmaras IP reais da rede local; ainda não foi verificado contra uma câmara USB ligada fisicamente. O `/stream` limita os espectadores simultâneos com `--max-clients` (por omissão 5, um 503 real a partir daí) para proteger a ligação Wi-Fi limitada de um CM5 contra um número ilimitado de fluxos simultâneos. O pipeline completo GStreamer/PyGObject de que o `config gst`/`config mediamtx` apenas geram a descrição, e a inferência Hailo-8 real, continuam a precisar desse ambiente de execução real e de um módulo Hailo-8 real, que este ambiente não tem. Veja o [`CHANGELOG.md`](CHANGELOG.md) para saber exatamente o que foi entregue até agora e "Estado atual e próximos passos" abaixo para o que continua em aberto. O `/stream` corta também um espectador que deixa de ler passados 30 segundos (um tempo limite de socket), para que um cliente bloqueado não possa reter para sempre um dos lugares do `--max-clients`.

**Vários espectadores, saúde e credenciais:** cada espectador de uma câmara recebe todos os frames (o buffer partilhado já não é consumido pelo primeiro leitor), `GET /health` responde `200` enquanto chegam frames e `503` caso contrário (`connecting`, `stalled`, `given_up`), e se todas as tentativas de religação se esgotarem o processo termina agora com erro em vez de servir um fluxo vazio, para que o seu supervisor o reinicie. As palavras-passe dos URL RTSP são mascaradas nos registos e mensagens; passe o URL com `--device-env VAR` (uma variável de ambiente) em vez de `--device` para que não apareça na lista de processos. Os anfitriões, dispositivos e caminhos RTSP são validados antes de serem escritos num pipeline gerado, e o pipeline de uma câmara IP usa `rtspsrc` com filas limitadas que descartam.

---

## 2. 🔄 ARQUITETURA PREVISTA DO PIPELINE

O diagrama abaixo é o fluxo de dados de destino para que este projeto está a ser construído - a *forma* dele (que elemento alimenta qual, a divisão `Tee`) está fixada pelo `pipeline.py` e é gerada hoje como sintaxe real de `gst-launch-1.0`, mas nada neste diagrama é executado ainda: isso precisa do ambiente de execução real V4L2/GStreamer/Hailo-8 e de câmaras USB físicas.

```mermaid
graph LR
    USB[8x USB Cameras] --> V4L2[V4L2 Capture]
    V4L2 --> ISP[Hardware ISP<br/>Resize/Format]
    ISP --> TEE[Tee Element]
    TEE --> HAI[Hailo NPU Inference]
    TEE --> DISP[Local Display / Stream]
```

---

## 3. 🧠 INFORMAÇÃO TÉCNICA AVANÇADA

### Porque não há `hardware/`, `firmware/`, `os/` nem `models/` aqui

O CM5 + Hailo-8 é hardware comercial sem placa própria para desenhar, ao contrário das placas STM32H745/STM32G474 à medida dentro do [HYDRA-UMC](https://github.com/JuanenRac/HYDRA-UMC) - pelo que não existe pasta `hardware/`/`firmware/` em nenhum dos 5 projetos do Nó de IA de Visão. O `os/` (a imagem HydraOS partilhada) e o `models/` (os ficheiros `.hef` compilados realmente servidos à NPU) vivem apenas no pai de integração, [HYDRA-UMC-VISION-NODE](https://github.com/JuanenRac/HYDRA-UMC-VISION-NODE), já que é o processo que detém a imagem do anfitrião CM5 e o identificador do dispositivo Hailo-8 - levar cópias separadas para aqui seria apenas estado extra para manter sincronizado sem qualquer benefício.

### Forma prevista do pipeline

O elemento `Tee` do diagrama acima é a decisão de desenho fundamental já tomada antes da implementação: as tramas captadas/pré-processadas destinam-se a bifurcar-se para dois consumidores ao mesmo tempo - o caminho de inferência Hailo-8 (que alimenta o [HYDRA-UMC-VISION-NODE](https://github.com/JuanenRac/HYDRA-UMC-VISION-NODE)) e um ecrã local / fluxo RTSP-WebRTC opcional para monitorização humana - sem que o caminho de monitorização acrescente latência ao caminho de inferência.

### Decisões de desenho já tomadas

* **Versão lida dos metadados do pacote instalado, não fixada no código** - o `main.py` chama `importlib.metadata.version("hydra-umc-vision-streamer")` em vez de uma segunda cadeia `__version__`, para que o `bump_version.py` só tenha um sítio para editar e os dois nunca possam divergir.
* **A subida ao estilo conta-quilómetros só toca automaticamente em `PATCH`/`MINOR`** - o `bump_version.py` transporta o `PATCH` para o `MINOR` depois de 9 e o `MINOR` para o `MAJOR` depois de 9, mas nunca sobe o próprio `MAJOR`; essa é uma decisão humana deliberada, a mesma convenção do `HYDRA-UMC-EDITOR-URDF/bump_version.py` e do `HYDRA-UMC-SUITE/bump_version.py`.
* **O YAML do MediaMTX é escrito à mão, não construído sobre o PyYAML** - a forma da saída do `mediamtx_config.py` (um mapa `paths:` plano, uma entrada `source: publisher` por câmara) é simples e fixa o suficiente para que uma dependência real ainda não se justifique. Reveja se a configuração por câmara passar a ter campos aninhados ou em lista.
* **O pipeline e a configuração do MediaMTX têm de concordar num só caminho RTSP por câmara** - o `rtsp_url_for()` é o único sítio que o deriva (a partir do nome da câmara), para que o `config gst` e o `config mediamtx` nunca possam discordar sobre onde vive o fluxo de uma câmara.
* **O `FrameBuffer` descarta a trama mais antiga, não a mais recente, quando fica cheio.** O vídeo em direto não tem uso para uma acumulação crescente de tramas antigas - a trama mais recente é sempre a útil. Uma fila que bloqueasse os produtores arriscaria a própria thread real de captura, e uma fila que simplesmente continuasse a crescer arriscaria exatamente a falha de memória ilimitada que esta porta existe para impedir.
* **O `reconnect.py` nunca dorme nem toca ele próprio num socket real.** O `ConnectionTracker` apenas acompanha o estado e devolve quanto tempo quem chama deve esperar - essa separação é o que torna todo o calendário de recuo (incluindo desistir depois de `max_attempts`) exatamente reproduzível num teste, sem relógio real nem ligação de câmara real.

---

## 📂 ESTRUTURA DE DIRETÓRIOS

```text
HYDRA-UMC-VISION-STREAMER/
├── src/                 # Código-fonte (pacote hydra_umc_vision_streamer)
│   └── hydra_umc_vision_streamer/
│       ├── config.py           # Análise/validação da configuração por câmara
│       ├── pipeline.py         # Geração da descrição do pipeline GStreamer
│       ├── mediamtx_config.py  # Geração do paths.yml do MediaMTX
│       ├── buffer.py           # Memória intermédia real e limitada de tramas (contrapressão que descarta a mais antiga)
│       ├── reconnect.py        # Política real e determinística de religação/recuo
│       ├── hailo_runtime.py    # Fronteira real de integração de inferência HailoRT (hailo_platform), importada sob demanda
│       ├── mjpeg_server.py     # Servidor MJPEG real - serve de facto a imagem de uma webcam USB ou câmara IP RTSP por HTTP
│       └── main.py             # Ponto de entrada da CLI (invocação simples + `config`/`stream`)
├── tests/               # Suite pytest real (config, pipeline, mediamtx, buffer, reconnect, hailo_runtime, mjpeg_server, CLI)
├── docs/                # Documentação e guias de afinação
├── build/               # Saída da compilação (o .venv local também vive aqui)
├── images/              # Multimédia e diagramas
├── systemd/
│   ├── hydra-umc-vision-streamer@.service  # Unidade systemd instanciada por câmara
│   └── cameras.env.example                 # Exemplo de ficheiro de ambiente por instância
├── tools/
│   ├── build_test.py    # Verificação de compilação sem subir a versão (sem subida de versão/CHANGELOG)
│   └── ci_validate.py   # Validação de manifesto/CHANGELOG/documentação usada pelo CI
├── pyproject.toml       # Metadados do pacote, dependências, versão ao estilo conta-quilómetros
├── bump_version.py      # Subida de versão nativa ao estilo conta-quilómetros (executada pelo build.sh/.bat)
├── bump_manifest_version.py # Sincroniza a versão do hydra-umc.project.json com a nativa (--sync)
├── build.sh / build.bat # venv + instalação editável + verificação de compilação + testes
├── run.sh / run.bat     # Executa o ponto de entrada a partir do venv local
└── CHANGELOG.md         # Histórico versão a versão (esquema conta-quilómetros, sem datas)
```

Sem pastas `hardware/`, `firmware/`, `os/` nem `models/` - veja "Informação técnica avançada" acima para saber porquê. O `os/` e o `models/` vivem apenas no pai de integração, [HYDRA-UMC-VISION-NODE](https://github.com/JuanenRac/HYDRA-UMC-VISION-NODE).

---

## 🏗️ GUIA DE COMPILAÇÃO E EXECUÇÃO

### Pré-requisitos

* **Python 3.10 ou superior** no seu `PATH` (os scripts tentam `python3` e depois recorrem a `python`).
* Ainda não é necessário GStreamer, ferramentas V4L2 nem outra dependência nativa - **zero dependências de execução de terceiros** nesta fase (`dependencies = []` no `pyproject.toml`).
* Algumas dezenas de MB de espaço em disco para um ambiente virtual local em `.venv/`.

### Passo a passo

```bash
# Linux / macOS
./build.sh
```

1. **Subida de versão ao estilo conta-quilómetros** - executa o `bump_version.py`, incrementando o `PATCH` no `pyproject.toml` em cada compilação (transitando para `MINOR`/`MAJOR` segundo a regra acima).
2. **Ambiente virtual** - cria o `.venv/` se não existir; reutiliza-o caso contrário.
3. **Instalação editável** - `pip install -e ".[dev]"` para que as edições em `src/` tenham efeito de imediato, instala o `pytest` e regista o ponto de entrada de consola `hydra-umc-vision-streamer`.
4. **Verificação de compilação** - `python -m compileall -q src` compila para bytecode todos os ficheiros de `src/`, apanhando erros de sintaxe em todo o ecossistema mesmo em ficheiros que o `main.py` nunca importa.
5. **Suite de testes real** - `python -m pytest tests/ -q` (105 testes que cobrem a configuração (incluindo a análise de câmaras IP reais e a codificação percentual do `rtsp_url()`), o pipeline, a geração do MediaMTX, a política de memória intermédia/religação, a fronteira de integração com o HailoRT, o caminho de captura e serviço MJPEG e a CLI).

O `set -euo pipefail` pára o script no primeiro passo que falhar; a compilação só reporta êxito se os 5 passarem.

```bash
./run.sh
```

Localiza o interpretador dentro do `.venv` (tratando as estruturas POSIX e Windows do `.venv`) e executa `python -m hydra_umc_vision_streamer.main`, reencaminhando quaisquer argumentos - a invocação simples imprime nome + versão + papel.

Exemplo real - validar a configuração de uma câmara, gerar o seu pipeline GStreamer e gerar a configuração correspondente do relé MediaMTX:

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

Exemplo real - captar e servir de facto uma câmara como MJPEG por HTTP (o único subcomando que abre um dispositivo real):

```bash
# Dispositivo USB/V4L2
./run.sh stream serve --device 0 --port 8100

# Câmara IP RTSP real (verificada contra hardware real - veja o CHANGELOG.md)
CAMERA_URL="rtsp://admin:secret@192.168.0.211:554/11" ./run.sh stream serve --device-env CAMERA_URL --port 8100 --width 1920 --height 1080 --fps 15
```

Exemplo real - simular um consumidor lento contra uma memória intermédia limitada e uma ligação caída conduzida pela política real de religação:

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
:: Windows - passos idênticos, sintaxe batch
build.bat
run.bat
```

### Resolução de problemas

* **`python`/`python3` não encontrado** - instale o Python 3.10+ e confirme que está no `PATH`.
* **O `compileall` falha** - foi introduzido um erro de sintaxe real em `src/`; a compilação pára sem tocar na instalação, de propósito.
* **"No `.venv` found" do `run.sh`/`run.bat`** - execute primeiro o `build.sh`/`build.bat` pelo menos uma vez; o `run` nunca cria o ambiente.
* **Instalação editável obsoleta** - apague o `.venv/` e recompile; raramente necessário, já que o `pip install -e .` normalmente apanha as alterações ao código em direto.

---

## 🚀 Estado atual e próximos passos

**O que funciona hoje:** a validação da configuração por câmara, a geração da descrição do pipeline GStreamer e a geração da configuração do relé MediaMTX (`config.py`, `pipeline.py`, `mediamtx_config.py`), uma memória intermédia de tramas real e demonstravelmente limitada e uma política real e determinística de religação (`buffer.py`, `reconnect.py`, `stream simulate`), uma fronteira real de integração com o HailoRT (`hailo_runtime.py`) pronta para um módulo Hailo-8 real no momento em que se ligue, e um caminho v0 real de captura e serviço (`mjpeg_server.py`, `stream serve`) que abre um dispositivo USB/V4L2 real **ou uma câmara IP RTSP real** (`source_type: "ip"` no `config.py`, `cv2.CAP_FFMPEG` no `mjpeg_server.py`) através do OpenCV e serve MJPEG real por HTTP - instalável num CM5 através do `provisioning/install_vision_streamer.sh` do próprio `HYDRA-UMC-OS` (uma instância systemd por ranhura de câmara atribuída pelo administrador, `systemd/hydra-umc-vision-streamer@.service`) e já consumido em direto pelo proxy `GET /api/camera/:id/stream` do `HYDRA-UMC-SERVER` e pelas vistas de câmara do `HYDRA-UMC-STUDIO`. O caminho de câmaras IP está verificado de ponta a ponta contra hardware real: as 4 câmaras IP reais da rede local abriram e transmitiram tramas reais por todo o caminho real - 105 testes no total, mais um pacote Python real e instalável com um ponto de entrada verificado.

**O que continua em aberto, sem ordem particular, sem calendário comprometido e dependente de hardware real:**

* Executar de facto o *pipeline gerado* - o tee completo GStreamer/PyGObject para um ramo de inferência Hailo-8, e não o `stream serve` mais simples baseado em OpenCV da v0 acima - através de um ambiente de execução real.
* Redimensionamento / conversão de formato pelo ISP por hardware (precisa do ISP real do CM5).
* Executar de facto inferência através do `hailo_runtime.py` (precisa de um módulo Hailo-8 real e de um `.hef` compilado real) e analisar o formato de saída NMS desse modelo real - deliberadamente não adivinhado sem o dispositivo para o verificar.
* Saída WebRTC e controlo de exposição/ganho por câmara (precisa do dispositivo V4L2 real).
* O `stream serve` ainda não foi verificado contra uma câmara USB real e ligada fisicamente - apenas contra uma câmara IP RTSP real e contra o `cv2.VideoCapture` simulado na fronteira do módulo (veja `tests/test_mjpeg_server.py`).

---

## 🔗 Projetos relacionados

Este projeto faz parte do ecossistema de robótica HYDRA-UMC do mesmo autor (JuanenRac / Electro Hobby 3D). Vale a pena conhecê-los, porque um pedido pode ser, na verdade, sobre um destes e não sobre este repositório.

**Projeto-mãe**
- **[HYDRA-UMC-VISION-NODE](https://github.com/JuanenRac/HYDRA-UMC-VISION-NODE)** — centro de integração do pipeline de visão Hailo-8, com uma verificação real de prontidão de hardware por etapa; o projeto-mãe de que este repositório é uma etapa ou consumidor específico, dentro do seu próprio pipeline de perceção.

**Projetos irmãos** — as outras etapas/consumidores do próprio pipeline de perceção Hailo-8 do HYDRA-UMC-VISION-NODE
- **[HYDRA-UMC-DETECTION-HEF](https://github.com/JuanenRac/HYDRA-UMC-DETECTION-HEF)** — registo real de modelos compilados com verificação segura de carga por arquitetura Hailo e soma de verificação.
- **[HYDRA-UMC-SAFETY-ZONES](https://github.com/JuanenRac/HYDRA-UMC-SAFETY-ZONES)** — lógica v0 de violação de zonas, atualidade da calibração e pedido de E-STOP que lê as posições dos objetos de um ficheiro; nenhum detetor a alimenta e ainda não há E-STOP físico ligado.
- **[HYDRA-UMC-VISUAL-SERVOING-API](https://github.com/JuanenRac/HYDRA-UMC-VISUAL-SERVOING-API)** — lei de correção de servovisão baseada em posição com autorização condicionada ao estado da zona; ainda sem estimativa de pose por câmara.

**Também fazem parte do ecossistema**

*Hardware e plataforma centrais*
- **[HYDRA-UMC](https://github.com/JuanenRac/HYDRA-UMC)** — o desenho da placa-mãe do braço robótico: anfitrião CM5 + STM32H745 de dois núcleos, pensado para orquestrar até 8 braços de ferramenta por CAN-OTA/SPI-OTA (firmware numa fase inicial; ainda sem placa montada).
- **[HYDRA-UMC-OS](https://github.com/JuanenRac/HYDRA-UMC-OS)** — camada de produto reproduzível do Raspberry Pi OS para o CM5: agente só de leitura, configuração/perfis validados, aprovisionamento Wi-Fi de primeiro contacto.
- **[HYDRA-UMC-SDK](https://github.com/JuanenRac/HYDRA-UMC-SDK)** — o contrato JSON-Schema partilhado e a fronteira de software de controlo de trabalhos contra a qual cada bridge valida os seus comandos (não é uma função de segurança certificada).
- **[HYDRA-UMC-CONNECTOR-HUB](https://github.com/JuanenRac/HYDRA-UMC-CONNECTOR-HUB)** — registo declarativo de manifestos de adaptador e validador para conectores de máquinas externas; estende a ideia de contrato do SDK a máquinas externas sem substituir os projetos de gateway industrial.

*Backend central e clientes*
- **[HYDRA-UMC-SERVER](https://github.com/JuanenRac/HYDRA-UMC-SERVER)** — o back-end headless real (REST/WebSocket) com que todos os clientes de controlo realmente comunicam.
- **[HYDRA-UMC-STUDIO](https://github.com/JuanenRac/HYDRA-UMC-STUDIO)** — painel web de controlo com visualização 3D em tempo real de vários robôs.
- **[HYDRA-UMC-SUITE](https://github.com/JuanenRac/HYDRA-UMC-SUITE)** — centro de comando de enxame para desktop (PySide6) para vários servidores ao mesmo tempo, empacotado como executável independente.
- **[HYDRA-UMC-ANDROID-CONTROL](https://github.com/JuanenRac/HYDRA-UMC-ANDROID-CONTROL)** — aplicação Android nativa de controlo, com início de sessão biométrico e um companheiro Wear OS emparelhado.
- **[HYDRA-UMC-IOS-CONTROL](https://github.com/JuanenRac/HYDRA-UMC-IOS-CONTROL)** — aplicação de controlo para iOS/iPadOS (Flutter) com sincronização WebSocket em tempo real.
- **[HYDRA-UMC-DSI](https://github.com/JuanenRac/HYDRA-UMC-DSI)** — interface tátil nativa para o ecrã tátil DSI de 7" integrado, executada no próprio CM5.
- **[HYDRA-UMC-EDITOR-URDF](https://github.com/JuanenRac/HYDRA-UMC-EDITOR-URDF)** — criador/editor gráfico de URDF para desktop que envia os modelos concluídos para o catálogo do STUDIO.
- **[HYDRA-UMC-EDITOR-STL](https://github.com/JuanenRac/HYDRA-UMC-EDITOR-STL)** — editor de modelos STL para desktop que transforma/substitui/remove/adiciona peças reais no mesmo catálogo de modelos que o HYDRA-UMC-EDITOR-URDF também edita.
- **[HYDRA-UMC-BRIDGE-AMR](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-AMR)** — fronteira de coordenação para frotas AGV/AMR através de um publicador MQTT VDA 5050 (testado apenas contra uma frota emulada).
- **[HYDRA-UMC-BRIDGE-CNC](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-CNC)** — coordenador de células CNC de alto nível com acesso ao estado GRBL e aos bytes de controlo (testado apenas contra um emulador).
- **[HYDRA-UMC-BRIDGE-DROIDS](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-DROIDS)** — fronteira de coordenação para droides com patas/humanoides, com um emissor de comandos para o Boston Dynamics Spot (testado apenas contra um emulador).
- **[HYDRA-UMC-BRIDGE-LASER](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-LASER)** — coordenador de células laser que lê 3 sinais GPIO (chave, caixa e interlock) (testado apenas contra um chip simulado; não pode armar nem disparar um laser).
- **[HYDRA-UMC-BRIDGE-OPENPNP](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-OPENPNP)** — coordenador seguro de fluxo de placa de alto nível para pick-and-place com OpenPnP.
- **[HYDRA-UMC-BRIDGE-PRINTER3D](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-PRINTER3D)** — fronteira de coordenação segura para impressoras 3D Moonraker/Klipper, com comandos de trabalho reais protegidos por portas.
- **[HYDRA-UMC-BRIDGE-ROS2](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-ROS2)** — coordenador com um transporte ROS 2 baseado em rclpy importado sob demanda (ainda não executado contra uma instalação ROS 2).
- **[HYDRA-UMC-BRIDGE-UAV](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-UAV)** — fronteira de coordenação para UAV com câmara, com um emissor de comandos MAVLink (testado apenas contra um emulador).

*Plataforma de ferramentas URTC*
- **[URTC](https://github.com/JuanenRac/URTC)** — firmware da placa física Universal Robot Tool Controller, mais de 25 perfis de ferramenta por barramento CAN.
- **[URTC-FLASHER](https://github.com/JuanenRac/URTC-FLASHER)** — ferramenta gráfica de gravação para desktop das placas URTC, por CAN-OTA e também SWD/JTAG de chip completo.
- **[URTC-TESTER](https://github.com/JuanenRac/URTC-TESTER)** — ferramenta de diagnóstico CAN em tempo real para desktop das placas URTC, com um painel por perfil de ferramenta.
- **[URTC-WEB-STUDIO](https://github.com/JuanenRac/URTC-WEB-STUDIO)** — alternativa no navegador ao URTC-TESTER através da Web Serial API, sem instalação local.

*Nó de IA cognitiva (Hailo-10)*
- **[HYDRA-UMC-COGNITIVE-NODE](https://github.com/JuanenRac/HYDRA-UMC-COGNITIVE-NODE)** — centro de integração do pipeline cognitivo do Hailo-10 (orquestração de LLM/VLA/voz).
- **[HYDRA-UMC-VLA-ENGINE](https://github.com/JuanenRac/HYDRA-UMC-VLA-ENGINE)** — codificação/descodificação real de tokens de ação e geração de trajetórias para um modelo Visão-Linguagem-Ação.
- **[HYDRA-UMC-VOICE-UI](https://github.com/JuanenRac/HYDRA-UMC-VOICE-UI)** — front-end de voz real (VAD + analisador de intenções) com um relé para o relógio limitado e protegido por confirmação.
- **[HYDRA-UMC-SEMANTIC-PLANNER](https://github.com/JuanenRac/HYDRA-UMC-SEMANTIC-PLANNER)** — decomposição real de tarefas baseada em regras e recuperação semântica de erros sobre os códigos de erro do MCU.
- **[HYDRA-UMC-DOCS-QA](https://github.com/JuanenRac/HYDRA-UMC-DOCS-QA)** — pesquisa real de documentos TF-IDF só com a biblioteca padrão sobre a documentação Markdown deste ecossistema.
- **[HYDRA-UMC-LOCAL-TECHNICIAN](https://github.com/JuanenRac/HYDRA-UMC-LOCAL-TECHNICIAN)** — técnico de manutenção de IA local, protegido por políticas, para o próprio ecossistema: observa, diagnostica e propõe correções; os dois níveis de maior risco não estão implementados de propósito.

*Orquestração e enxame*
- **[HYDRA-UMC-ORCHESTRATOR](https://github.com/JuanenRac/HYDRA-UMC-ORCHESTRATOR)** — centro de integração com um contrato real de relatório de saúde gRPC/Protobuf e uma máquina de estados de missões.
- **[HYDRA-UMC-JOB-DISPATCHER](https://github.com/JuanenRac/HYDRA-UMC-JOB-DISPATCHER)** — fila real de trabalhos por prioridade com deduplicação, sobre uma API HTTP real.
- **[HYDRA-UMC-NODE-HEALING](https://github.com/JuanenRac/HYDRA-UMC-NODE-HEALING)** — vigilante real de saúde da frota por gRPC com repetição/recuo e deteção de identidade incoerente.
- **[HYDRA-UMC-PATH-PLANNER-3D](https://github.com/JuanenRac/HYDRA-UMC-PATH-PLANNER-3D)** — planeador real de trajetórias 3D baseado em RRT com validação real de colisões com obstáculos e espaço de trabalho.
- **[HYDRA-UMC-SWARM-SYNC](https://github.com/JuanenRac/HYDRA-UMC-SWARM-SYNC)** — sincronização real de estado CRDT LWW-Element-Map, testada por propriedades para a convergência de várias células.

*Gémeo digital e simulação*
- **[HYDRA-UMC-TWIN](https://github.com/JuanenRac/HYDRA-UMC-TWIN)** — centro de integração do motor de gémeo digital, com um contrato real de sincronização de compatibilidade de versões.
- **[HYDRA-UMC-HIL-BRIDGE](https://github.com/JuanenRac/HYDRA-UMC-HIL-BRIDGE)** — encaminhador hardware-in-the-loop com um interlock de software de colisão entre a simulação e o hardware real (testado sem hardware real).
- **[HYDRA-UMC-PHYSICS-REPLICA](https://github.com/JuanenRac/HYDRA-UMC-PHYSICS-REPLICA)** — cinemática direta real e validação de limites de juntas sobre um subconjunto real de URDF.
- **[HYDRA-UMC-SYNTHETIC-DATA-GEN](https://github.com/JuanenRac/HYDRA-UMC-SYNTHETIC-DATA-GEN)** — gerador procedural real de cenas 2D com exportação de anotações YOLO/COCO.

*Dados e análise*
- **[HYDRA-UMC-DATALAKE](https://github.com/JuanenRac/HYDRA-UMC-DATALAKE)** — armazém real de séries temporais sobre sqlite3 com uma API HTTP real de ingestão/consulta.
- **[HYDRA-UMC-ANOMALY-DETECTOR](https://github.com/JuanenRac/HYDRA-UMC-ANOMALY-DETECTOR)** — detetor real de anomalias por FFT e linha de base estatística, com monitorização de deriva.
- **[HYDRA-UMC-PRODUCTION-REPORTS](https://github.com/JuanenRac/HYDRA-UMC-PRODUCTION-REPORTS)** — cálculo real de OEE/disponibilidade sobre o histórico do DATALAKE, com exportação CSV reprodutível.
- **[HYDRA-UMC-TELEMETRY-COLLECTOR](https://github.com/JuanenRac/HYDRA-UMC-TELEMETRY-COLLECTOR)** — pipeline real de ingestão CAN/WebSocket para o DATALAKE, com deduplicação por sequência.

*Gateway industrial*
- **[HYDRA-UMC-GATEWAY-INDUSTRIAL](https://github.com/JuanenRac/HYDRA-UMC-GATEWAY-INDUSTRIAL)** — centro de integração que retransmite para protocolos industriais, com uma camada real de lista de comandos permitidos e contrapressão.
- **[HYDRA-UMC-OPCUA-SERVER](https://github.com/JuanenRac/HYDRA-UMC-OPCUA-SERVER)** — espaço de endereços OPC-UA real, verificado com uma sessão de cliente real do protocolo binário.
- **[HYDRA-UMC-MQTT-BROKER](https://github.com/JuanenRac/HYDRA-UMC-MQTT-BROKER)** — broker MQTT real com autenticação opcional por cliente e ACL de tópicos.
- **[HYDRA-UMC-MTCONNECT-ADAPTER](https://github.com/JuanenRac/HYDRA-UMC-MTCONNECT-ADAPTER)** — endpoints XML MTConnect `/probe` e `/current` reais com saída em modo degradado.

*Ferramentas complementares e operações do ecossistema*
- **[HYDRA-UMC-DASHBOARD-AI](https://github.com/JuanenRac/HYDRA-UMC-DASHBOARD-AI)** — painéis de Resumos Inteligentes e Realce de Anomalias sobre o DATALAKE/ANOMALY-DETECTOR, com um recurso estatístico honesto.
- **[HYDRA-UMC-TOOL-CLI](https://github.com/JuanenRac/HYDRA-UMC-TOOL-CLI)** — CLI da frota com um contrato de códigos de saída real e estável, um cliente vivo genuíno da API do HYDRA-UMC-SERVER.
- **[HYDRA-UMC-WATCH](https://github.com/JuanenRac/HYDRA-UMC-WATCH)** — aplicação companheira WearOS com padrões de alerta tátil e um relé de voz para o telemóvel emparelhado (ainda não executada num relógio físico).
- **[URTC-SMART-RACK](https://github.com/JuanenRac/URTC-SMART-RACK)** — firmware de um rack de montagem de placas com descodificação real do ID da ferramenta e lógica de pré-aquecimento Smart Idle.
- **[URTC-VISION-TOOL](https://github.com/JuanenRac/URTC-VISION-TOOL)** — firmware mais um companheiro de visão em Python real para uma cabeça de ferramenta de inspeção térmica/RGB.
- **[HYDRA-UMC-UPDATER](https://github.com/JuanenRac/HYDRA-UMC-UPDATER)** — ferramenta administrativa de desktop que descobre, clona e atualiza todos os repositórios deste ecossistema.
- **[HYDRA-UMC-OS-REBUILDER](https://github.com/JuanenRac/HYDRA-UMC-OS-REBUILDER)** — ferramenta de desktop para Windows/Linux que constrói uma imagem do CM5 pronta a gravar com as versões mais recentes do ecossistema, com configuração de primeiro arranque de Wi-Fi/utilizador/SSH ao estilo do Raspberry Pi Imager.
- **[HYDRA-UMC-OPS-AGENT](https://github.com/JuanenRac/HYDRA-UMC-OPS-AGENT)** — coordenador de incidentes de manutenção: um papel de borda de poucos privilégios recolhe um inventário/estado higienizado, um papel de plano de controlo mostra-o só de leitura e pede a um fornecedor de IA que sugira um diagnóstico; nunca aplica um patch nem implanta nada.
- **[HYDRA-UMC-DEV-SERVER](https://github.com/JuanenRac/HYDRA-UMC-DEV-SERVER)** — anfitrião de desenvolvimento reproduzível (Raspberry Pi 5 / CM5) que guarda o código-fonte do ecossistema e executa tarefas limitadas de compilação/teste numa fila durável; um papel de desenvolvimento dedicado, explicitamente não um CM5 operacional.

---

## 📚 Documentação e comunidade

- **[docs/CLI_REFERENCE.md](docs/CLI_REFERENCE.md)** — cada subcomando (`config validate`/`gst`/`mediamtx`, `stream simulate`/`serve`, incluindo exemplos reais de câmaras USB e IP RTSP), com saída real capturada.
- **[CONTRIBUTING.md](CONTRIBUTING.md)** — pilha tecnológica e diretrizes de código para um pull request.
- **[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)** — as normas de comportamento esperadas nesta comunidade.
- **[SECURITY.md](SECURITY.md)** — como comunicar uma vulnerabilidade e as áreas de segurança em que este projeto se concentra.
- **[SUPPORT.md](SUPPORT.md)** — onde fazer perguntas e comunicar erros.
- **[LICENSE.md](LICENSE.md)** — a licença deste projeto.

## 👤 AUTOR
**JuanenRac** (Electro Hobby 3D)
📧 electrohobby3d@gmail.com
📺 [youtube.com/@electrohobby3d](https://youtube.com/@electrohobby3d)

## 📜 LICENÇA
GPL-3.0-or-later - consulte LICENSE para mais detalhes.

