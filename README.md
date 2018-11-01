# NRF52840_MicroPython_OTA_Updates
Micropython code to update the receiver's code "over the air" using Nordic's nRF52 proprietary radio

Here's a simple demo:
1.  You load rxRadio_v009.py as main.py onto an nRF52840 that's running micropython.  This is the receiver node.  Then you type 'receive()' at the >>> REPL prompt on the receiver node.
2.  You load txRadio_v009.py as main.py and update.txt onto a different nRF52840 that's also running micropython.  This is the transmitter node.  Update.txt is the code that you want the receiver node to be running.  For testing purposes, you could simply copy rxRadio_v009.py to update.txt and use that.  Or, better, you could start with that and then modify it in some way.  Then you type 'transmit()' at the >>> REPL prompt on the transmitter node.

The transmitter node will then transmit the update.txt file to the receiver node.  The receiver node will acknowledge each packet it receives and ask for the next one, so if a packet is lost, the transmitter just keeps retransmitting it until it hears that the receiver has acknowledged receipt.  After the entire update.txt file is trasmitted, the transmitter will then transmit an SHA-256 hash code for update.txt to the receiver.  As a cross-check, the receiver will compute it's own SHA-256 hash code for the update.txt file that it received.  If the two hash codes match, then the update.txt file was successfully transmitted.  If so, update.txt is copied to main.py on the receiver node and the receiver node then reboots.  From that point onward, the receiver node will be running the updated code.  

Enjoy!

P.S. Concrete suggestions on how to improve the code are always welcome!

LEGAL DISCLAIMER:  I am making no representations or warranties.  None whatsoever.  If  you want to use it, do so solely at your own risk and make sure you test it adequately for whatever your purposes may be.

