import uos
import ujson
import network
import ntptime
import utime
from machine import WDT, reset, RTC
# last_wdt = 0
wdt = None


def import_json(file_name):
    dic = {}
    if file_name in uos.listdir():
        with open(file_name) as f:
            dic = ujson.loads(f.read())
    return dic


def start_wdt(wdt_config):
    global wdt
#    global last_wdt
#    if 'last_wdt' not in globals() :
#        last_wdt = 0
    if wdt_config:
        wdt = WDT(timeout=10000)  # enable it with a timeout of 10s
        wdt.feed()
#        last_wdt = utime.time()
        return True
    else:
        return False


def feed_wdt(id = None):
    # global last_wdt
    global wdt
    if wdt:
        wdt.feed()
#        if last_wdt + 5 < utime.time():
#            with open("error.log", "a") as f:
#                f.write('WDT warning id:{} wait {} sec at time {}\n'.format(id, utime.time() - last_wdt), utime.time())
#        last_wdt = utime.time()


def wifi_connect(ap_list):
    global print_queue
    timeout = 10
    station = network.WLAN(network.STA_IF)

    if station.isconnected():
        print_queue.append("Wifi Already connected")
        return True

    station.active(True)

    if isinstance(ap_list, dict):
        ap_list = [ap_list]
    if isinstance(ap_list, list):
        for ap in ap_list:
            start = utime.time()
            station.connect(ap['ssid'], ap['password'])
            print(ap['ssid'], ap['password'])
            while not station.isconnected() and utime.time() < start + timeout:
                utime.sleep(1)
                print('wait')
                feed_wdt()

    if not station.isconnected():
        print_queue.append("Wifi Connection timeout")
        return False
    else:
        return True


def set_ntp_time():  # Set ntp time
    global status, print_queue
    ntp_set = False
    while not ntp_set:
        try:
            ntptime.settime()
            status['env']['timestamp'] = utime.time()
            ntp_set = True
        except OSError:
            print_queue.append("ntptime timeout")
            tm = utime.gmtime(status['env']['timestamp'])
            RTC().datetime((tm[0], tm[1], tm[2], tm[6] + 1, tm[3], tm[4], tm[5], 0))

    return ntp_set


print_queue = []

try:
    lc = import_json('local-config.json')
    if 'wdt' not in lc:
        lc['wdt'] = False
    wdt_started = start_wdt(lc['wdt'])
    config = import_json('config.json')
    status = import_json('status.json')
    status['services'] = {'wdt': wdt_started, 'network': False, 'ntp': False, 'webrepl': False, 'gcp': False,
                          'ph_control': False, 'temp_control': False, 'refill': False}

    if 'network' in lc and 'ap_list' in lc['network']:
        status['services']['network'] = wifi_connect(lc['network']['ap_list'])

    status['services']['ntp'] = set_ntp_time()

    a = utime.gmtime()

    boot_msg = 'Starting at {:4d}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}Z'.format(a[0], a[1], a[2], a[3], a[4], a[5])
    print_queue = [boot_msg]

    if 'boot' not in status:
        status['boot'] = []
    status['boot'].insert(0, boot_msg)
    if len(status['boot']) > 5:
        status['boot'].pop()

    with open('boot.log', 'a') as f:
        for line in print_queue:
            f.write('{}\n'.format(line))

except Exception as e:
    import sys
    a = utime.gmtime()
    boot_err = 'Starting at {:4d}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}Z'.format(a[0], a[1], a[2], a[3], a[4], a[5])
    with open("error.log", "a") as f:
        f.write(boot_err)
        sys.print_exception(e, f)
    if lc['wdt']:
        reset()

# To do : garder config- wdt dans boot. Transferer wifiConnect  et NTP dans main avec une tache de surveillance et
# mise à jour du NTP dans un fichier status mettre le NTP à jour en faisant l'hypothèse qu'en cas de redémarrage sans
# NTP on vient d'un reboot wdt et on peut utiliser un temps sauvegardé

