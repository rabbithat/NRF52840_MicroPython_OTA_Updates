

# This program for an nRF52840 or nRF52832 receives a string on the radio and prints the string
# Start the program by typing:
# start()
# at the REPL >>> prompt.

# You can use:
# ampy --port /dev/ttyACM0 put main.py
# from LINUX to load main.py onto a nRF52 board

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

NRF_POWER = const(0x40000000)
DCDCEN = const(0x578)
NRF_POWER___DCDCEN = const(NRF_POWER + DCDCEN)

NRF_CLOCK = const(0x40000000)
TASKS_HFCLKSTART = const(0)
EVENTS_HFCLKSTARTED = const(0x100)
NRF_CLOCK___TASKS_HFCLKSTART = const(NRF_CLOCK + TASKS_HFCLKSTART)
NRF_CLOCK___EVENTS_HFCLKSTARTED = const(NRF_CLOCK + EVENTS_HFCLKSTARTED)

NRF_RADIO = const(0x40001000)
BASE0 = const(0x51C)
PREFIX0 = const(0x524)
FREQUENCY = const(0x508)
PCNF1 = const(0x518)
PCNF0 = const(0x514)
MODE = const(0x510)
MODECNF0 = const(0x650)
CRCCNF = const(0x534)
PACKETPTR = const(0x504)
RXADDRESSES = const(0x530)
TXPOWER = const(0x50C)
TASKS_DISABLE = const(0x010)
STATE = const(0x550)
TASKS_TXEN = const(0)
TASKS_RXEN = const(0x004)
EVENTS_READY = const(0x100)
TASKS_START = const(0x008)
EVENTS_END = const(0x10C)
EVENTS_CRCOK = const(0x130)
NRF_RADIO___BASE0 = const(NRF_RADIO + BASE0)
NRF_RADIO___PREFIX0 = const(NRF_RADIO + PREFIX0)
NRF_RADIO___FREQUENCY = const(NRF_RADIO + FREQUENCY)
NRF_RADIO___PCNF1 = const(NRF_RADIO + PCNF1)
NRF_RADIO___PCNF0 = const(NRF_RADIO + PCNF0)
NRF_RADIO___MODE = const(NRF_RADIO + MODE)
NRF_RADIO___MODECNF0 = const(NRF_RADIO + MODECNF0)
NRF_RADIO___CRCCNF = const(NRF_RADIO + CRCCNF)
NRF_RADIO___PACKETPTR = const(NRF_RADIO + PACKETPTR)
NRF_RADIO___RXADDRESSES = const(NRF_RADIO + RXADDRESSES)
NRF_RADIO___TXPOWER = const(NRF_RADIO + TXPOWER)
NRF_RADIO___TASKS_DISABLE = const(NRF_RADIO + TASKS_DISABLE)
NRF_RADIO___STATE = const(NRF_RADIO + STATE)
NRF_RADIO___TASKS_TXEN = const(NRF_RADIO + TASKS_TXEN)
NRF_RADIO___TASKS_RXEN = const(NRF_RADIO + TASKS_RXEN)
NRF_RADIO___EVENTS_READY = const(NRF_RADIO + EVENTS_READY)
NRF_RADIO___TASKS_START = const(NRF_RADIO + TASKS_START)
NRF_RADIO___EVENTS_END = const(NRF_RADIO + EVENTS_END)
NRF_RADIO___EVENTS_CRCOK = const(NRF_RADIO + EVENTS_CRCOK)

def initializeSerialOutput():
    print("Starting...")

def initializeHardware():  # enable the DCDC voltage regulator
    machine.mem32[NRF_POWER___DCDCEN] = 1  # NRF_POWER->DCDCEN=1;   
    
def initializeClocks():    # activate the high frequency crystal oscillator
    # NRF_CLOCK->TASKS_HFCLKSTART=1;  
    machine.mem32[NRF_CLOCK___TASKS_HFCLKSTART] = 1 
    # wait until high frequency clock start is confirmed
    # while (NRF_CLOCK->EVENTS_HFCLKSTARTED==0) {};  
    while (machine.mem32[NRF_CLOCK___EVENTS_HFCLKSTARTED] == 0):
        True
        
def initializeRadio():
    # print this node's address in hexadecimal
    print("My address is 0x{:02X}".format(my_prefixAddress) + "{:08X}".format(my_baseAddress))
          
    machine.mem32[NRF_RADIO___BASE0] = my_baseAddress
    machine.mem32[NRF_RADIO___PREFIX0] = my_prefixAddress
    
    # value must be between 0 and 100
    machine.mem32[NRF_RADIO___FREQUENCY] = 98  # 2498Mhz.  
    # Enable data whitening.    
    # Base address is 4 bytes long (possible range is 2 to 4) and 
    # max size of payload is 255,and 0 bytes of static length payload
    machine.mem32[NRF_RADIO___PCNF1] = 0x400FF  # 0x020400FF
    # Use 8-bit preamble, and LENGTH can be 8 bits long.  S0 and S1 are all zero bits long.
    machine.mem32[NRF_RADIO___PCNF0] = 0x00000008
    
    machine.mem32[NRF_RADIO___MODE] = 0  # set 1Mbps datarate.
    machine.mem32[NRF_RADIO___MODECNF0] = 1  # enable fast ramp-up of radio from DISABLED state.
    
    machine.mem32[NRF_RADIO___CRCCNF] = 3  # CRC will be 3 (3 is max) bytes and is computed including the address field
    machine.mem32[NRF_RADIO___PACKETPTR] = radioBuffer_address  # pointer to the payload in radioBuffer
    
    machine.mem32[NRF_RADIO___RXADDRESSES] = 1  # receive on logical address 0.  Not important for transmitting.
    machine.mem32[NRF_RADIO___TXPOWER] = 4  # set to 4db transmit power, which is the maximum. max for nRF52840 is 8db
    
    machine.mem32[NRF_RADIO___TASKS_DISABLE] = 1  # DISABLE the radio to establish a known state.
    while (machine.mem32[NRF_RADIO___STATE] != 0):  # wait until radio is DISABLED (i.e. STATE=0);
        True
        
    machine.mem32[NRF_RADIO___TASKS_RXEN] = 1  # turn on the radio receiver and shift into RXIDLE.
    while (machine.mem32[NRF_RADIO___EVENTS_READY] == 0):  # Busy-wait.  After event READY, radio shall be in state RXIDLE.
        True
    
    # ASSERTION: radio now in RXIDLE mode
    # Note: radio much move from RXIDLE mode into RX mode in order to receive    
    machine.mem32[NRF_RADIO___EVENTS_CRCOK] = 0  # clear the semaphore
    machine.mem32[NRF_RADIO___TASKS_START] = 1  # Move from RXIDLE mode into RX mode.


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
    machine.mem32[NRF_RADIO___EVENTS_CRCOK] = 0  # clear the semaphore
    while (not (finishedReceivingSha255String)):
        if (machine.mem32[NRF_RADIO___EVENTS_CRCOK] != 0):
            machine.mem32[NRF_RADIO___EVENTS_CRCOK] = 0 # clear the semaphore
            theReceivedString=receivedString()
            print("Received string = ",theReceivedString)
            if (theReceivedString == "$!$!$!$!"):  # Use $!$!$!$! to signify end of sha-256 hash
                print("Terminating reception of hash.")
                finishedReceivingSha255String = True
            else:    
                receivedHash = receivedHash + theReceivedString   
                print("Received hash = ",receivedHash)   
                machine.mem32[NRF_RADIO___TASKS_START] = 1  # Move from RXIDLE mode into RX mode to receive another packet
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
        if (machine.mem32[NRF_RADIO___EVENTS_CRCOK] != 0):
            machine.mem32[NRF_RADIO___EVENTS_CRCOK] = 0 # clear the semaphore
            packetCounter = packetCounter + 1
            theReceivedString=receivedString()
            machine.mem32[NRF_RADIO___TASKS_START] = 1  # Move from RXIDLE mode into RX mode so that next packet isnt missed
            # meanwhile, process the packet already received 
            receivedPacketId = int(theReceivedString[0:10])
            if (receivedPacketId == receivedPacketIdTracker + 1):
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






