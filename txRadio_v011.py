# This program for an nRF52840 transmitter node sends the file "update.txt" to an nRF52840 receiver node,
# which then copies the received file to main.py and reboots.
# This accomplishes an "over the air" (OTA) update of the micropython code running on the receiver node.

# You can use:
# ampy --port /dev/ttyACM0 put update.txt
# from LINUX to load the update code onto the nRF52840 transmitter board

# Start program by typing:
# transit()
# at the REPL >>> prompt.

# ATTRIBUTIONS: Thank you to Peter Hinch (aka "pythoncoder") for his suggestions on how 
# to improve the efficiency of variables declared with const(..) and also on a more efficient
# way to copy a string to the radioBuffer by using memoryview.

# Any concrete suggestions on how to improve the code are always appreciated.

from micropython import const  # needed to efficiently access memory by avoiding micropython lookups
import machine  # so can peek and poke different registers on the nRF5x
import uctypes # needed to create the radio buffer (a byte array)
import utime # needed to create delays
import gc #import garbage collector
import uhashlib # needed for SHA-256
import ubinascii # needed to convert the SHA-256 result into a string

radioBuffer_size = 256
radioBuffer = bytearray(radioBuffer_size)  # allocate IO buffer for use by nRF5x radio
radioBuffer_address = uctypes.addressof(radioBuffer)

_target_prefixAddress = const(0xAA) # prefix address of the other node
_target_baseAddress = const(0xDEADBEEF) # base address of the other node
_my_prefixAddress = const(0xAA)  # prefix address of this node
_my_baseAddress = const(0xFEEDBEEF)  # base address of this node


_NRF_POWER = const(0x40000000)
_DCDCEN = const(0x578)
_NRF_POWER___DCDCEN = const(_NRF_POWER + _DCDCEN)

_NRF_CLOCK = const(0x40000000)
_TASKS_HFCLKSTART = const(0)
_EVENTS_HFCLKSTARTED = const(0x100)
_NRF_CLOCK___TASKS_HFCLKSTART = const(_NRF_CLOCK + _TASKS_HFCLKSTART)
_NRF_CLOCK___EVENTS_HFCLKSTARTED = const(_NRF_CLOCK + _EVENTS_HFCLKSTARTED)

_NRF_RADIO = const(0x40001000)
_BASE0 = const(0x51C)
_PREFIX0 = const(0x524)
_FREQUENCY = const(0x508)
_PCNF1 = const(0x518)
_PCNF0 = const(0x514)
_MODE = const(0x510)
_MODECNF0 = const(0x650)
_CRCCNF = const(0x534)
_PACKETPTR = const(0x504)
_RXADDRESSES = const(0x530)
_TXPOWER = const(0x50C)
_TASKS_DISABLE = const(0x010)
_STATE = const(0x550)
_TASKS_TXEN = const(0)
_TASKS_RXEN = const(0x004)
_EVENTS_READY = const(0x100)
_TASKS_START = const(0x008)
_EVENTS_END = const(0x10C)
_EVENTS_CRCOK = const(0x130)
_NRF_RADIO___BASE0 = const(_NRF_RADIO + _BASE0)
_NRF_RADIO___PREFIX0 = const(_NRF_RADIO + _PREFIX0)
_NRF_RADIO___FREQUENCY = const(_NRF_RADIO + _FREQUENCY)
_NRF_RADIO___PCNF1 = const(_NRF_RADIO + _PCNF1)
_NRF_RADIO___PCNF0 = const(_NRF_RADIO + _PCNF0)
_NRF_RADIO___MODE = const(_NRF_RADIO + _MODE)
_NRF_RADIO___MODECNF0 = const(_NRF_RADIO + _MODECNF0)
_NRF_RADIO___CRCCNF = const(_NRF_RADIO + _CRCCNF)
_NRF_RADIO___PACKETPTR = const(_NRF_RADIO + _PACKETPTR)
_NRF_RADIO___RXADDRESSES = const(_NRF_RADIO + _RXADDRESSES)
_NRF_RADIO___TXPOWER = const(_NRF_RADIO + _TXPOWER)
_NRF_RADIO___TASKS_DISABLE = const(_NRF_RADIO + _TASKS_DISABLE)
_NRF_RADIO___STATE = const(_NRF_RADIO + _STATE)
_NRF_RADIO___TASKS_TXEN = const(_NRF_RADIO + _TASKS_TXEN)
_NRF_RADIO___TASKS_RXEN = const(_NRF_RADIO + _TASKS_RXEN)
_NRF_RADIO___EVENTS_READY = const(_NRF_RADIO + _EVENTS_READY)
_NRF_RADIO___TASKS_START = const(_NRF_RADIO + _TASKS_START)
_NRF_RADIO___EVENTS_END = const(_NRF_RADIO + _EVENTS_END)
_NRF_RADIO___EVENTS_CRCOK = const(_NRF_RADIO + _EVENTS_CRCOK)

def initializeSerialOutput():
    print("Starting...")

def initializeHardware():  # enable the DCDC voltage regulator
    machine.mem32[_NRF_POWER___DCDCEN] = 1  # NRF_POWER->DCDCEN=1;   
    
def initializeClocks():    
    machine.mem32[_NRF_CLOCK___TASKS_HFCLKSTART] = 1 # activate the high frequency crystal oscillator
    # wait until high frequency clock start is confirmed
    while (machine.mem32[_NRF_CLOCK___EVENTS_HFCLKSTARTED] == 0):
        True
    # ASERTION: High frequency clock now activated and running

def initializeRxMode():        
    machine.mem32[_NRF_RADIO___BASE0] = _my_baseAddress
    machine.mem32[_NRF_RADIO___PREFIX0] = _my_prefixAddress

    machine.mem32[_NRF_RADIO___TASKS_DISABLE] = 1  # DISABLE the radio to establish a known state.
    while (machine.mem32[_NRF_RADIO___STATE] != 0):  # wait until radio is DISABLED (i.e. STATE=0);
        True
    machine.mem32[_NRF_RADIO___TASKS_RXEN] = 1  # turn on the radio transmitter and shift into RXIDLE.
    while (machine.mem32[_NRF_RADIO___EVENTS_READY] == 0):  # Busy-wait.  After event READY, radio shall be in state TXIDLE.
        True    
    # ASSERTION: now ready to receive a packet.


def initializeTxMode():
    machine.mem32[_NRF_RADIO___BASE0] = _target_baseAddress
    machine.mem32[_NRF_RADIO___PREFIX0] = _target_prefixAddress


    machine.mem32[_NRF_RADIO___TASKS_DISABLE] = 1  # DISABLE the radio to establish a known state.
    while (machine.mem32[_NRF_RADIO___STATE] != 0):  # wait until radio is DISABLED (i.e. STATE=0);
        True
    machine.mem32[_NRF_RADIO___TASKS_TXEN] = 1  # turn on the radio transmitter and shift into TXIDLE.
    while (machine.mem32[_NRF_RADIO___EVENTS_READY] == 0):  # Busy-wait.  After event READY, radio shall be in state TXIDLE.
        True    
    # ASSERTION: now ready to transmit a packet.

def initializeRadio():
    # value must be between 0 and 100
    machine.mem32[_NRF_RADIO___FREQUENCY] = 98  # 2498Mhz.  
    
    # Enable data whitening.
    # Base address is 4 bytes long (possible range is 2 to 4) and 
    # max size of payload is 255,and 0 bytes of static length payload
    machine.mem32[_NRF_RADIO___PCNF1] = 0x020400FF  # 0x020400FF
    # Use an 8-byte preamble, and LENGTH can be 8 bits long.  S0 and S1 are all zero bits long.
    machine.mem32[_NRF_RADIO___PCNF0] = 0x03000008
    
    machine.mem32[_NRF_RADIO___MODE] = 1  # set 2Mbps datarate.
    machine.mem32[_NRF_RADIO___MODECNF0] = 1  # enable fast ramp-up of radio from DISABLED state.
    
    machine.mem32[_NRF_RADIO___CRCCNF] = 3  # CRC will be 3 (3 is max)  bytes and is computed including the address field
    machine.mem32[_NRF_RADIO___PACKETPTR] = radioBuffer_address  # pointer to the payload in radioBuffer
    
    machine.mem32[_NRF_RADIO___RXADDRESSES] = 1  # receive on logical address 0.  Not important for transmitting.
    machine.mem32[_NRF_RADIO___TXPOWER] = 8  # set to 8db transmit power, which is the maximum. 
    

        

mv = memoryview(radioBuffer)

def copyStringToRadioBuffer(s):
    l = len(s)
    mv[: l] = s.encode('utf8')[: l]
    mv[l] = 0  

def sendShortStrings(payloadCounter,theString,maxSubStringLength):
    stringLength = len(theString)
    if (stringLength > 0):
        index = 0
        maxIndex = stringLength + 1
        while (index<maxIndex):
            stopIndex = index + maxSubStringLength  
            if (stopIndex > maxIndex):
                stopIndex = maxIndex
            payloadCounter = payloadCounter + 1
            #print("payloadCounter=", payloadCounter)
            payloadCounterString =  ("{:<10}".format(str(payloadCounter)))
            #print("payloadCounterString = ", payloadCounterString)
            stringSubset = theString[index:stopIndex]
            txString=payloadCounterString + stringSubset
            #print("txString = ", txString)
            copyStringToRadioBuffer(txString)
            index = stopIndex 
            #print("Radio Buffer = ", radioBuffer)
            transmissionSucceeded = False  #transmission not yet sent
            while (not transmissionSucceeded):
                print(txString)
                initializeTxMode()
                machine.mem32[_NRF_RADIO___EVENTS_END] = 0  #Clear Semaphore
                while (machine.mem32[_NRF_RADIO___EVENTS_END] != 0): True  # wait
                machine.mem32[_NRF_RADIO___TASKS_START] = 1  # Move from TXIDLE mode into TX mode to transmit the packet
                while (machine.mem32[_NRF_RADIO___EVENTS_END] == 0): True  # busy-wait until packet is sent
                initializeRxMode()
                machine.mem32[_NRF_RADIO___EVENTS_CRCOK] = 0  # clear the semaphore
                while (machine.mem32[_NRF_RADIO___EVENTS_CRCOK] != 0): True  # wait until Semaphore clear is confirmed
                machine.mem32[_NRF_RADIO___TASKS_START] = 1  # Move from RXIDLE mode into RX mode to receive a packet
                #currentTime=utime.time_ms()
                #timeOutTime = currentTime + 200  # timeout in 200ms
                #utime.sleep_ms(200)  # sleep for a 100ms after transmitting to give the receiver node time to acknowledge the transmission   
                busyWaitCounter=0  
                while ((not machine.mem32[_NRF_RADIO___EVENTS_CRCOK]) and (busyWaitCounter < 10000)): 
                    busyWaitCounter = busyWaitCounter + 1
  # wait until acknowledgement received or time out
                if (machine.mem32[_NRF_RADIO___EVENTS_CRCOK]):
                    transmissionSucceeded = True         
                    print ("Transmitted: ", txString)

        return payloadCounter


def send(theString):
    # if (len(theString)>(radioBuffer_size - 1)):  # if string to be transmitted is too long
        # theString = theString[0:radioBuffer_size] # then cut it down the maximum length allowed
    copyStringToRadioBuffer(theString)
    print("Radio Buffer = ", radioBuffer)
    machine.mem32[_NRF_RADIO___EVENTS_END] = const(0)
    machine.mem32[_NRF_RADIO___TASKS_START] = 1  # Move from TXIDLE mode into TX mode to transmit the packet
    while (machine.mem32[_NRF_RADIO___EVENTS_END] == const(0)): True  # busy-wait until packet is sent
    print ("Finished transmitting: " + theString)


def printFile(theFileName):
    f=open(theFileName)
    lineOfFile = f.read()
    while lineOfFile:
        print(lineOfFile)
        lineOfFile = f.read()
    f.close()

def transmitUpdate():
    start()
    theFile="update.txt"
    payloadCounter = 0 #each payload is numbered
    f=open(theFile)
    line = f.readline()
    while (line):
        payloadCounter=sendShortStrings(payloadCounter,line,20)
        print(line)
        gc.collect()
        #print("Memory allocated:  ", gc.mem_alloc())
        #print("Memory free:  ", gc.mem_free())
        #gc.collect()
        #utime.sleep_ms(500)  # sleep for a second after transmitting the line to give the receiver time to process the  line
        line = f.readline()
    f.close()   
    payloadCounter=sendShortStrings(payloadCounter,"$$$$$$$$",20)
    theHash = computeFileHash(theFile)
    payloadCounter=sendShortStrings(payloadCounter,theHash,20)
    payloadCounter=sendShortStrings(payloadCounter,"$!$!$!$!",20)

def transmit():
    transmitUpdate()


def computeFileHash(theFile):
    f=open(theFile)
    theHash = uhashlib.sha256()
    line = f.readline()
    while line:
        theHash.update(line)
        line = f.readline()
    theRawHash = theHash.digest() # type is 'bytes'
    hexHash =  ubinascii.hexlify(theRawHash) # still 'bytes', but now in hex
    return hexHash.decode()  # hexHash coverted to a string type   

    
def initializeEverything():
    # Main setup    
    initializeSerialOutput()
    initializeHardware()
    initializeClocks()
    initializeRadio() 
    initializeTxMode()

def start():
    initializeEverything()
    print("Ready to transmit.")



print()
print("Hello.  I am the transmitter node.")
print("My address is 0x{:02X}".format(_my_prefixAddress) + "{:08X}".format(_my_baseAddress))
# print full target address in hexadecimal
print("The target address is 0x{:02X}".format(_target_prefixAddress) + "{:08X}".format(_target_baseAddress))
print ("Put update code in a file named 'update.txt'")
print ("Type 'transmit()' at the REPL prompt to begin OTA update transmission.")
          

   
