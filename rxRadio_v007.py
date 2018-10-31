# This program for an nRF52840 receiver node receive the file "update.txt" fro an nRF52840 transmitter node.
# After verifying the correctness of the file, the receiver node copies it to main.py and reboots.
# This accomplishes an "over the air" (OTA) update of the micropython code running on the receiver node.

# Start program by typing:
# receive()
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

my_prefixAddress = const(0xAA)
my_baseAddress = const(0xDEADBEEF)

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
    # wait until high frequency clock is confirmed to be started:
    while (machine.mem32[_NRF_CLOCK___EVENTS_HFCLKSTARTED] == 0):
        True
        
def initializeRadio():         
    machine.mem32[_NRF_RADIO___BASE0] = my_baseAddress
    machine.mem32[_NRF_RADIO___PREFIX0] = my_prefixAddress
    
    # value must be between 0 and 100
    machine.mem32[_NRF_RADIO___FREQUENCY] = 98  # 2498Mhz.  
    # Enable data whitening.    
    # Base address is 4 bytes long (possible range is 2 to 4) and 
    # max size of payload is 255,and 0 bytes of static length payload
    machine.mem32[_NRF_RADIO___PCNF1] = 0x400FF  # 0x020400FF
    # Use 8-bit preamble, and LENGTH can be 8 bits long.  S0 and S1 are all zero bits long.
    machine.mem32[_NRF_RADIO___PCNF0] = 0x00000008
    
    machine.mem32[_NRF_RADIO___MODE] = 0  # set 1Mbps datarate.
    machine.mem32[_NRF_RADIO___MODECNF0] = 1  # enable fast ramp-up of radio from DISABLED state.
    
    machine.mem32[_NRF_RADIO___CRCCNF] = 3  # CRC will be 3 (3 is max) bytes and is computed including the address field
    machine.mem32[_NRF_RADIO___PACKETPTR] = radioBuffer_address  # pointer to the payload in radioBuffer
    
    machine.mem32[_NRF_RADIO___RXADDRESSES] = 1  # receive on logical address 0.  Not important for transmitting.
    machine.mem32[_NRF_RADIO___TXPOWER] = 4  # set to 4db transmit power, which is the maximum. max for nRF52840 is 8db
    
    machine.mem32[_NRF_RADIO___TASKS_DISABLE] = 1  # DISABLE the radio to establish a known state.
    while (machine.mem32[_NRF_RADIO___STATE] != 0):  # wait until radio is DISABLED (i.e. STATE=0);
        True
        
    machine.mem32[_NRF_RADIO___TASKS_RXEN] = 1  # turn on the radio receiver and shift into RXIDLE.
    while (machine.mem32[_NRF_RADIO___EVENTS_READY] == 0):  # Busy-wait.  After event READY, radio shall be in state RXIDLE.
        True
    
    # ASSERTION: radio now in RXIDLE mode
    # Note: radio much move from RXIDLE mode into RX mode in order to receive    
    machine.mem32[_NRF_RADIO___EVENTS_CRCOK] = 0  # clear the semaphore
    machine.mem32[_NRF_RADIO___TASKS_START] = 1  # Move from RXIDLE mode into RX mode.


def copyStringToRadioBuffer(theString):
    stringLength=len(theString)
    i=0
    while (i<stringLength):
        radioBuffer[i]=ord(theString[i])
        i=i+1
    radioBuffer[i]=0  # delimit the end of the string


def copyRadioBufferToString(i):
#    if (radioBuffer[i]==0):
#        print("Radio buffer length = ", i)
#        return " "  # null string
#    else:
#        return chr(radioBuffer[i])+copyRadioBufferToString(i+1)
    returnString=""
    i=0
    while (radioBuffer[i] != 0):
        returnString = returnString + chr(radioBuffer[i])
        i=i+1
    return returnString

def receivedString():
    # print("Radio Buffer = ",radioBuffer)
    return copyRadioBufferToString(0)


def printFile(fileName):
    f=open(fileName)
    lineOfFile = f.read()
    while lineOfFile:
        print(lineOfFile)
        lineOfFile = f.read()
    f.close()

def copyFile(sourceFile,destinationFile):
    print("Starting copy of ",sourceFile, " onto ", destinationFile)
    s=open(sourceFile)
    d = open(destinationFile,"w")
    line=s.readline()
    while line:
        d.write(line)
        line=s.readline()
    s.close()
    d.close()
    print("Finished copying ",sourceFile, " onto ", destinationFile)    

def backupMainPy():
    print("Starting backup....")
    copyFile("main.py","backup.py")
    print("Finished backup.")

def receiveSha256StringFromTransmitter():
    print("Ready and waiting to receive SHA-256 from transmitter.")
    finishedReceivingSha255String=False
    receivedHash=""  
    machine.mem32[_NRF_RADIO___EVENTS_CRCOK] = 0  # clear the semaphore
    while (not (finishedReceivingSha255String)):
        if (machine.mem32[_NRF_RADIO___EVENTS_CRCOK] != 0):
            machine.mem32[_NRF_RADIO___EVENTS_CRCOK] = 0 # clear the semaphore
            theReceivedString=receivedString()
            print("Received string = ",theReceivedString)
            if (theReceivedString == "$!$!$!$!"):  # Use $!$!$!$! to signify end of sha-256 hash
                print("Terminating reception of hash.")
                finishedReceivingSha255String = True
            else:    
                receivedHash = receivedHash + theReceivedString   
                print("Received hash = ",receivedHash)   
                machine.mem32[_NRF_RADIO___TASKS_START] = 1  # Move from RXIDLE mode into RX mode to receive another packet
            gc.collect() 
    print("Received SHA-255 hash is", receivedHash)
    return receivedHash       
        
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
    print("rxRadio version 6.000")
    # backupMainPy()
    initializeSerialOutput()
    initializeHardware()
    initializeClocks()
    initializeRadio() 

def testReceiveSha():
    initializeEverything()
    print(receiveSha256StringFromTransmitter())

def start():
    initializeEverything()
    print("Waiting to receive update.txt file...")

    # Main loop
    f=open("update.txt","w")
    packetCounter = 0
    receivedHash=""
    timeToAssembleHash = False
    finishedReceiving = False

    timeToCloseReceiveFile = False
    receivedPacketIdTracker = 0
    while (not (finishedReceiving)):
        gc.collect()
        if (machine.mem32[_NRF_RADIO___EVENTS_CRCOK] != 0):
            machine.mem32[_NRF_RADIO___EVENTS_CRCOK] = 0 # clear the semaphore
            packetCounter = packetCounter + 1
            theReceivedString=receivedString()
            machine.mem32[_NRF_RADIO___TASKS_START] = 1  # Move from RXIDLE mode into RX mode so that next packet isnt missed
            # meanwhile, process the packet already received 
            receivedPacketId = int(theReceivedString[0:10])
            if (receivedPacketId == receivedPacketIdTracker + 1):  #filter out redundant packets
                print(receivedPacketId)
                receivedPacketIdTracker = receivedPacketIdTracker + 1
                receivedPayload = theReceivedString[10:]
                #print("receivedPacketId = ",receivedPacketId, " receivedPayload = ", receivedPayload)   
                #print(packetCounter, "Payload received:  " + theReceivedString)

                if (receivedPayload == "$$$$$$$$"):  # Use $$$$$$$$ to signify end of file transmission
                    timeToCloseReceiveFile = True
                    f.close()  #close the update.txt file
                    timeToAssembleHash = True
                else:
                    if (receivedPayload == "$!$!$!$!"):  # Use $!$!$!$! to signify end of hash transmission
                        finishedReceiving = True
                    else:
                        if (timeToAssembleHash):
                            receivedHash = receivedHash + receivedPayload               
                        else:
                            if (not timeToCloseReceiveFile):  
                                f.write(receivedPayload)       


    print()
    print()
    print("Here is the received fie:")
    printFile("update.txt")
    print("Received SHA-256 hash is:  ", receivedHash)
    computedHash = computeFileHash("update.txt")
    print ("Computed SHA-256 hash of received file is ", computedHash)
    if (receivedHash  == computedHash):
        print("Sucess!  Hash values match.  File successfully received.")
        copyFile("update.txt","main.py")
        print("Rebooting....")
        machine.reset() 
    else:
        print("Fail!  Hash values do NOT match.  Failed to receive update file successfully.  Update aborted.")

def receive():
    start()


print()
print ("Hello.  I am a receiver node.")
# print this node's full address in hexadecimal
print("My address is 0x{:02X}".format(my_prefixAddress) + "{:08X}".format(my_baseAddress))
print ("I am ready to perform an over-the-air code update.")
print("Type 'receive()' at the REPL prompt to begin.")







