import upip
import network

# Wifi connection
ssid = "FreeboxHL"
password =  "Chipie764"

def wifiConnect():
    import network

    station = network.WLAN(network.STA_IF)

    if station.isconnected() == True:
        print("Already connected")
        return

    station.active(True)
    station.connect(ssid, password)

    while station.isconnected() == False:
        pass

    print("Connection successful")
    print(station.ifconfig())
    
wifiConnect()
upip.install("micropython-umqtt.simple")
