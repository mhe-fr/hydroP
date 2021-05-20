
# D34/A6 Capteur PH -> D16 Moteur pompe PS acide
# D35/A7 Capteur conductivité C1 -> D17 Moteur pompe PS engrais
# D13/Touch4  Capteur niveau réserve C2
# D12/Touch5 Capteur niveau bac Hydro  C3-> D2 Pompe arrosage bac hydro
# D14/A16 Capteur humidité bac terre C4 -> D15 arrosage bac terre
# D33 Capteur température C7 -> D0 Résistance chauffage (niveau bac hydro)
# D27/A17 Capteur courant pompe circulation C5

import sys
import webrepl
import uasyncio
import utime
import onewire
import ds18x20
import gcp_iot
import json
# import uos
import gc
import ubinascii
from machine import WDT, TouchPad, Pin, ADC, reset


def start_web_repl():
    global status
    if status['services']['network'] and not status['services']['webrepl']:
        webrepl.start(password='kcid01')
        status['services']['webrepl'] = True


def IOTcommand(topic, msg_bytes):
    global status, print_queue, peristaltic_queue, refill_queue
    msg = msg_bytes.decode("utf-8")
    print_queue.append("topic :{}, msg:{} \n".format(topic, msg))
    msg_array = msg.split(':')
    if msg_array[0] == 'set' and len(msg_array) == 4:
        if msg_array[1] in ['refill', 'ph_control', 'temp_control']:
            if msg_array[2] in config[msg_array[1]] and msg_array[2] != 'start':
                try:
                    a = int(msg_array[3])
                    config[msg_array[1]][msg_array[2]] = a
                except ValueError:
                    a = 0
    if msg_array[0] == 'set' and len(msg_array) == 3:
        if msg_array[1] in ['wdt', 'webrepl'] and msg_array[2] in ['on', 'off']:
            lc[msg_array[1]] = (msg_array[2] == 'on')
        if msg_array[1] in ['refill', 'ph_control', 'temp_control'] and msg_array[2] in ['on', 'off']:
            config[msg_array[1]]['start'] = (msg_array[2] == 'on')
    if msg_array[0] == 'start' and len(msg_array) == 2:
        if msg_array[1] in ['refill', 'ph_control', 'temp_control']:
            status['services'][msg_array[1]] = True
    if msg == 'write' or msg[0:4] == 'set:':
        with open('local-config.json', 'w') as outfile:
            json.dump(lc, outfile)
        with open('config.json', 'w') as outfile:
            json.dump(config, outfile)
    if msg == 'reset':
        reset()
    if msg == 'start:webrepl':
        start_web_repl()
    if msg[0:6] == 'do:ph:':
        print_queue.append('msg append to the queue peristaltic')
        peristaltic_queue.append(msg)
    if msg[0:10] == 'do:refill:':
        print_queue.append('msg append to the queue refill')
        refill_queue.append(msg)
    if msg == 'print':
        print_queue.append('status = {}'.format(json.dumps(status)))
        print_queue.append('lc = {}'.format(json.dumps(lc)))
        print_queue.append('config = {}'.format(json.dumps(config)))

    return    


def read_temp(ow_sensors, address):
    ow_sensors.convert_temp()
    utime.sleep_ms(200)
    temp = 0
    for x in range(0, 3):
        try:
            temp = ow_sensors.read_temp(address)
            break
        except onewire.OneWireError:
            temp = 99.9
            continue
    return round(temp, 1)


def read_ph_sensor():
    buf = []
    for i in range(50):
        buf.append(ph_mesure.read())
        utime.sleep_ms(2)
    mean = 0
    for x in buf:
        mean += x
    mean = round(mean / len(buf), 1)
    mean_max = 0
    count = 0
    for x in buf:
        if x >= mean:
            mean_max += x
            count += 1
    mean_max = round(mean_max / count, 1)

    ph = round(conv_ph(mean), 1)
    print_queue.append('pH read raw avg:{} minMax:{} range:{} pH:{}'.format(mean, mean_max, max(buf) - min(buf), ph))
    return ph


# 2.9 1688   6.3 1491  17°C
# 2021.03.21 1482 = pH 7.0 (solution tampon) 1782 = pH 2.6 
# 2021.03.23 1482 = pH 7.0 (solution tampon) 1700 = pH 4.0 (solution tampon) 18°C
def conv_ph(analog):
    return 4.0 + (1700 - analog)/(1700-1482) * (7.0-4.0)


async def coro_peristaltic_driver():
    global peristaltic_queue
    while True:
        if len(peristaltic_queue) > 0:
            msg = peristaltic_queue.pop(0)
            if msg[0:6] == 'do:ph:':
                try:
                    a = int(msg[6:])
                except ValueError:
                    a = 0
                if 1 <= a < 10:
                    print_queue.append("{} on going".format(msg))
                    pHPump.value(1)
                    await uasyncio.sleep(a)
                    pHPump.value(0)

        await uasyncio.sleep(10)


async def coro_refill_driver():
    global refill_queue
    while True:
        if len(refill_queue) > 0:
            msg = refill_queue.pop(0)
            if msg[0:10] == 'do:refill:':
                try:
                    a = int(msg[10:])
                except ValueError:
                    a = 0
                if 15 <= a < 180:
                    print_queue.append("{} on going".format(msg))
                    refillPump.value(0)
                    await uasyncio.sleep(a)
                    refillPump.value(1)

        await uasyncio.sleep(10)


async def coro_read_env():
    global status
    while True:
        try:
            ambiant_temp = read_temp(ds, air_temp_ow_add)
            water_temp = read_temp(ds, water_temp_ow_add)
        except onewire.OneWireError:
            ambiant_temp = +100
            water_temp = +100
        status['env']['air_temp'] = ambiant_temp
        status['env']['water_temp'] = water_temp

        pHRefillPump.value(0)
        await uasyncio.sleep(60)
        pHRefillPump.value(1)
        await uasyncio.sleep(60)
        status['env']['ph'] = read_ph_sensor()
        await uasyncio.sleep(600-120)


async def check_message():
    while True:
        try:
            esp32.check_msg()
        except OSError:
            print_queue.append('Read error')
            esp32.disconnect()
            status['services']['gcp'] = False
            pass
        await uasyncio.sleep(2)


async def coro_ph_control():
    global peristaltic_queue, status
    while True:
        await uasyncio.sleep(15*60)
        if status['env']['ph'] > config['ph_control']['setpoint'] and status['services']['ph_control']:
            peristaltic_queue.append('do:ph:4')
        await uasyncio.sleep(15*60)


async def coro_temp_control():
    global status
    while True:
        if status['env']['water_temp'] < config['temp_control']['setpoint'] and status['services']['temp_control']:
            heater.value(0)  # heater on
        else:
            heater.value(1)  # heater off
        await uasyncio.sleep(15*60)


async def coro_refill():
    global refill_queue, config, status
    every_h = config['refill']['every_h']
    start_h = config['refill']['start_h']
    duration_s = config['refill']['duration_s']
    h_now = utime.time()/3600
    schedule_h_refill = ((h_now + every_h - start_h) // every_h) * every_h + start_h
    while True:
        await uasyncio.sleep(60)
        if schedule_h_refill * 3600 < utime.time() and status['services']['refill']:
            refill_queue.append('do:refill:{}'.format(duration_s))
            schedule_h_refill += every_h


async def store_state():
    global status, print_queue
    periode = 60*10
    schedule_time = ((utime.time() // periode) + 1) * periode
    while True:
        # print_queue.append(b'utime.time() : {}, schedule_time : {}'.format(utime.time(), schedule_time))

        if utime.time() >= schedule_time:
            gc.collect()
            print_queue.append("start : {}".format(utime.time()))
            a = utime.gmtime()
            timestamp = '{:4d}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}Z'.format(a[0], a[1], a[2], a[3], a[4], a[5])
            msg = ('{{"ambientTemp" : {:.1f}, "waterTemp" : {:.1f}, "pH" : {:.1f}, "waterLowLevelHydro" : {:.0f}, '
                   '"waterHighLevelHydro" : {:.0f}, "timestamp" : "{}"}}')\
                .format(status['env']['air_temp'], status['env']['water_temp'], status['env']['ph'], 0, 0, timestamp)
            string = ''
            for item in status:
                string += '{}: {}\n'.format(item, json.dumps(status[item]))
            retry = 3
            while retry > 0:
                try:
                    if status['services']['gcp']:
                        esp32.publish('/devices/{dev-id}/events'.format(**{'dev-id': lc['gcp']['DEVICE_ID']}), msg)
                        esp32.publish('/devices/{dev-id}/state'.format(**{'dev-id': lc['gcp']['DEVICE_ID']}), string)
                except OSError:
                    retry -= 1
                    print_queue.append('publish timeout')
                    await uasyncio.sleep(2)
                    if retry == 0:
                        status['services']['gcp'] = False
                        esp32.disconnect()
                        retry = 0
                else:
                    retry = 0
                    schedule_time += periode
                    print_queue.append(msg)
                    status['env']['timestamp'] = utime.time()
                    with open('status.json', 'w') as outfile:
                        json.dump(status, outfile)

        feed_wdt()
        await uasyncio.sleep(2)


async def sanity_check():
    global print_queue
    start = utime.time()
    counter = 0
    wheel = ['/', '-', '\\', '|']
    while True:
        if not status['services']['network']:
            if 'network' in lc and 'ap_list' in lc['network']:
                status['services']['network'] = wifi_connect(lc['network']['ap_list'])
        if not status['services']['ntp']:
            status['services']['ntp'] = set_ntp_time()
        if not status['services']['gcp']:
            status['services']['gcp'] = gcp_connect(lc)
        s = '{} time:{} fm:{}'.format(wheel[counter % 4], round((utime.time() - start) / 60, 1), gc.mem_free())
        print(s, end='')
        await uasyncio.sleep(2)
        if len(print_queue) == 0:
            print('\b' * len(s), end='')
        else:
            print(' ' * (25-len(s)), end='')
        counter += 1
        while len(print_queue) > 0:
            print(print_queue.pop(0))
        feed_wdt()


def gcp_connect(lc):
    global esp32
    esp32.connect()
    esp32.subscribe('/devices/{device-id}/commands/#'.format(**{'device-id': lc['gcp']['DEVICE_ID']}))
    return gcp_iot.CONNECTED

global config, status, lc, print_queue, esp32

peristaltic_queue = []
refill_queue = []

# create output pin 
pHPump = Pin(16, Pin.OUT, value=0)
fertilizerPump = Pin(17, Pin.OUT, value=0)  # 26 gr pour  100 secondes = 0.26ml/s
refillPump = Pin(2, Pin.OUT, value=1)  # 1 is off
sprinklePump = Pin(15, Pin.OUT, value=1)  # 1 is off
heater = Pin(0, Pin.OUT, value=1)  # 1 is off
pHRefillPump = Pin(4, Pin.OUT, value=1)  # 1 is off
blueLed = Pin(5, Pin.OUT, value=1)  # 1 is off

# set one wire for DS18B20 temp sensor
ds = ds18x20.DS18X20(onewire.OneWire(Pin(33)))

water_temp_ow_add = ubinascii.unhexlify(config['devices']['water_temp_ow_addr'])
air_temp_ow_add = ubinascii.unhexlify(config['devices']['air_temp_ow_addr'])

# set analog input
ph_mesure = ADC(Pin(34))
ph_mesure.atten(ADC.ATTN_11DB)

# set capacitive input
# waterLowLevelHydroSensor = TouchPad(Pin(12))
# waterHighLevelHydroSensor = TouchPad(Pin(13))

feed_wdt()

# show new start
blueLed.value(0)
utime.sleep_ms(1000)
blueLed.value(1)

feed_wdt()

if lc['webrepl']:
    start_web_repl()

esp32 = gcp_iot.GCPIOT(lc['gcp']['PROJECT_ID'], lc['gcp']['CLOUD_REGION'], lc['gcp']['REGISTRY_ID'],
                       lc['gcp']['DEVICE_ID'], lc['gcp']['KEYFILE'], lc['gcp']['CERTFILE'], IOTcommand, 2)

status['services']['gcp'] = gcp_connect(lc)
feed_wdt()

# scan for devices on the bus
roms = ds.scan()
print_queue.append('oneWire devices found: {}'.format(roms))

feed_wdt()

for serv in ['refill', 'ph_control', 'temp_control']:
    if config[serv]['start']:
        status['services'][serv] = True


def _handle_exception(the_loop, context):
    print('Global handler')
    sys.print_exception(context["exception"])
    the_loop.stop()
    sys.exit()  # Drastic - loop.stop() does not work when used this way


loop = uasyncio.get_event_loop()
# loop.set_exception_handler(_handle_exception)
loop.create_task(coro_peristaltic_driver())  # Schedule ASAP
loop.create_task(coro_refill_driver())  # Schedule ASAP
loop.create_task(store_state())  # Schedule ASAP
loop.create_task(check_message())  # Schedule ASAP
loop.create_task(coro_read_env())  # Schedule ASAP
loop.create_task(coro_ph_control())  # Schedule ASAP
loop.create_task(coro_temp_control())  # Schedule ASAP
loop.create_task(coro_refill())  # Schedule ASAP
loop.create_task(sanity_check())  # Schedule ASAP

try:
    loop.run_forever()
except Exception as e:
    with open("error.log", "a") as f:
        sys.print_exception(e, f)
finally:
    if lc['wdt']:
        reset()
