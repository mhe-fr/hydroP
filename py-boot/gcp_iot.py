import ussl
import utime
import ucryptolib
import ubinascii
import uhashlib
import gc
from umqtt.simple import MQTTClient

DISCONNECTED = 0
CONNECTING = 1
CONNECTED = 2
GOOGLEMQTTHOST = "mqtt.googleapis.com"
EPOCH_GAP_SEC = 946684800  # 01/01/1970 (linux) to 01/01/2000 (embedded mp ntptime) = 10957 days * (24 * 3600) sec/days

def cleanBase64(src) :
    ret = ubinascii.b2a_base64(src)[:-1]
    rest = len(src) % 3
    if rest != 0 :
        return ret[:-3 + rest ]
    return ret

class GCPIOT:

    def __init__(self, project_id, cloud_region, registry_id, device_id, keyfile, certfile, callback=None):
        self.project_id = project_id
        self.cloud_region = cloud_region
        self.registry_id = registry_id
        self.device_id = device_id
        with open(keyfile, 'r') as f:
            self.keyData = f.read()
        self.connection = None
        self.iat = None
        self.exp = 0
        self.lastEventDate = None
        self.state = DISCONNECTED
        self.callback = callback
        
    def _isAlive(self):
        return (utime.time() + EPOCH_GAP_SEC < self.exp)  

    def _checkConnect(self):
        if not self._isAlive():
            self.disconnect()
            self.connect()
            print('Reconnect')
        
    def connect(self):

        while self.state != CONNECTED:
            self.iat = utime.time() + EPOCH_GAP_SEC
            self.exp = self.iat + (24 * 3600) 
            clientString = b'projects/'+ self.project_id + b'/locations/' + self.cloud_region + b'/registries/' + self.registry_id + b'/devices/' + self.device_id
            jwtheader = b'{"alg":"RS256","typ":"JWT"}'
            print(jwtheader)
            jwtpayload = b'{"aud":"' + self.project_id + b'","iat":' + str(self.iat) + b',"exp":' + str(self.exp)+ b'}'
            # print(jwtpayload)
            # print(self.keyData)
            rsacontext = ucryptolib.rsa(self.keyData)
            pkcs = ucryptolib.pkcs1v15(rsacontext)
            message = cleanBase64(jwtheader) + b'.' + cleanBase64(jwtpayload)
            hash = (uhashlib.sha256(message)).digest()
            # print("hash message: {} len:{} \n".format(hash,len(hash)))
            signature = cleanBase64(pkcs.sign(hash))
            jwt = message + b'.' + signature
            # print(jwt)
            try:
                self.state = CONNECTING
                self.connection = MQTTClient(client_id=clientString, user="johndoe", password=jwt, server=GOOGLEMQTTHOST, port=8883, keepalive=60*10, ssl=True)
                self.connection.connect()
                self.connection.set_callback(self.callback)
                self.state = CONNECTED
            except OSError:
                print('Could not establish MQTT connection')
                utime.sleep(0.5)
                raise


        print('MQTT LIVE!')

    def publish(self, topic, msg):
        self._checkConnect()
        if self.state == CONNECTED:
            return self.connection.publish(topic, msg)

    def subscribe(self, topic):
        self._checkConnect()
        if self.state == CONNECTED:
            return self.connection.subscribe(topic)

    def check_msg(self):
        self._checkConnect()
        if self.state == CONNECTED:
            return self.connection.check_msg()
            
    def disconnect(self):
        if self.state == CONNECTED:
            self.connection.disconnect()        
            self.state = DISCONNECTED


