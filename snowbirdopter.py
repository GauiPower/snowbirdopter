import os
import argparse
import serial
import struct
import sys
import platform
import subprocess
import math
from struct import *

class snowbirdopter:
    'Snowrbirdopter class to interact with the tiptoi''s snowbird processor'
    ser = None
    scsidev = None
    prompt = b'SNOWBIRD2-BIOS>#'
    validSerialDev = False
    validScsiDev = False

    def __init__(self, serport, scsidev, verbose=True):
        '''Initialize serial and optionally also SCSI device'''
        
        # initialize serial device
        if serport is not False:
            try:
                self.ser = serial.Serial(serport, 38400, timeout=2, bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE, stopbits=1, xonxoff=0, rtscts=0)
                self.validSerialDev = True
            except serial.serialutil.SerialException:
                if verbose:
                    print(r"[DEBUG] Serial device is not available." )
                raise ValueError('Serial device is not available.')

            if self.validSerialDev and verbose:
                    print(r"[DEBUG] Serial device port name: '{}'".format(self.ser.name) )
        
        # optionally also initialize SCSI device
        if scsidev is not False:
            self.scsidev = scsidev

            if verbose:
                print(r"[DEBUG] Generic SCSI device file name: '{}'".format( scsidev ) )

            proc = subprocess.run(["sg_inq", self.scsidev, "-H"], check=True, stdout=subprocess.PIPE, universal_newlines=True)
            if proc.returncode == 0 and "ANYKA" in proc.stdout and "STORAGE BOOT" in proc.stdout:
                if verbose:
                    print( "[DEBUG] SCSI inquiry successful." )
            else:
                raise ValueError('Generic SCSI device is not available.')

            proc = subprocess.run(["sg_raw", "-r", "64", self.scsidev, "F1", "01", "00", "00", "00", "00"], check=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE, universal_newlines=True)
            if proc.returncode == 0 and proc.stdout == '' and ("SCSI Status: Good \n\nReceived 13 bytes of data" in proc.stderr) and ("ANYKA DESIGNE" in proc.stderr):
                if verbose:
                    print( "[DEBUG] SCSI device identification successful." )
                self.validScsiDev = True
            else:
                raise ValueError('Generic SCSI device is available but has unexpected identifier.')

        # check if at least one device is valid (serial or SCSI)
        if not (self.validSerialDev or self.validScsiDev):
            print(r"[ERROR] Neither serial device nor generic SCSI device is available." )
            raise ValueError('No device available.')

    def readline(self, verbose=True):
        '''Read a line from the serial'''
        
        if not self.validSerialDev:
            print( r"[ERROR] No valid serial device." )
            return False

        line = self.ser.readline()
        if verbose:
            print(r"[INFO] Read from serial: {}".format(line) )

        line = line.decode("ascii").rstrip()
        return line

    def trx_line(self, line, rxEcho=True, checkEcho=True):
        '''Transmit a line from serial byte per byte and wait for echo after each byte; check returned value per default'''
        
        if not self.validSerialDev:
            print( r"[ERROR] No valid serial device." )
            return False

        for k in range(0, len(line)):
            cTx = line[k].to_bytes(1, byteorder='big')
            self.ser.write(cTx)
            if rxEcho:
                cRx = self.ser.read(1)
                if checkEcho and (cTx != cRx):
                    print(r"[ERROR] Tx: {} != Rx: {}".format( cTx, cRx ))
                    return False
        return True

        line = True
        while line:
            line = self.ser.readline()
            if line == self.prompt:
                # Prompt appeared, the dump has finished.
                break
            else:
                line = line.decode("ascii").rstrip()
                
                rawData = line.split('\t', 5)
                print( r"[INFO] {}".format( '  '.join(rawData) ) )

                # further processing to store it in a binary file
                # skip address as the memory values are in consecutive order without gaps
                for i in range(1, len(rawData) ):
                    value = int(rawData[i], 16)
                    if fp:
                        fp.write(value.to_bytes(4, byteorder='little', signed=False))

        if fp:
            fp.close()

        # check last line again
        if not line == self.prompt:
            return False
        else:
            return True

    def dump(self, startAddr, endAddr, filepath=None, verbose=True):
        '''Generic implementation of the dump command
         
        Execute dump command via serial or SCSI.
        '''

        if self.validScsiDev:
            ret = self.dump_scsi(startAddr, endAddr, filepath, verbose)
        else:
            ret = self.dump_serial(startAddr, endAddr, filepath, verbose)
        return ret

    def dump_serial(self, startAddr, endAddr, filepath=None, verbose=True):
        '''Implementation of the dump command (via serial)'''

        if not self.validSerialDev:
            print( r"[ERROR] No valid serial device." )
            return False

        cmd = b'dump\r'
        if not self.trx_line(cmd):
            return False

        if not self.rx_check_expected(b'Input start addr(0x08000000):'):
            return False

        addr = startAddr.encode('ascii') + b'\r'
        if not self.trx_line(addr):
            return False

        if not self.rx_check_expected(b'Input end addr(0x08000000):'):
            return False

        addr = endAddr.encode('ascii') + b'\r'
        if not self.trx_line(addr):
            return False

        header = b'   Adress \t    0   \t     4    \t     8    \t      c\n'
        if not self.rx_check_expected(header):
            return False

        fp = None
        if filepath:
            fp = open(filepath, "wb")
            if not fp:
                return False

        line = True
        while line:
            line = self.ser.readline()
            if line == self.prompt:
                # Prompt appeared, the dump has finished.
                break
            else:
                line = line.decode("ascii").rstrip()

                rawData = line.split('\t', 5)
                print( r"[INFO] {}".format( '  '.join(rawData) ) )

                # further processing to store it in a binary file
                # skip address as the memory values are in consecutive order without gaps
                for i in range(1, len(rawData) ):
                    value = int(rawData[i], 16)
                    if fp:
                        fp.write(value.to_bytes(4, byteorder='little', signed=False))

        if fp:
            fp.close()

        # check last line again
        if not line == self.prompt:
            return False
        else:
            return True

    def dump_scsi(self, startAddr, endAddr, filepath=None, verbose=True):
        '''Implementation of the dump command (via serial)'''
        
        if not self.validScsiDev:
            print( r"[ERROR] No valid SCSI device." )
            return False

        addressAsNum = int(startAddr, 16)
        endAddressAsNum = int(endAddr, 16)
        addr = startAddr.encode('ascii')

        if endAddressAsNum != addressAsNum:
            calcLenAsNum = endAddressAsNum - addressAsNum
        else:
            calcLenAsNum = 4 # if end and start address are equal, dump at least 4 bytes

        # dump length needs to be a multiple of 64 bytes, so round up to full 64 byte chunks
        dumpLenAsNum = math.ceil( calcLenAsNum/64 ) * 64
        dumpLen = str.format("{:08X}", dumpLenAsNum)
        if verbose:
            print( r"[DEBUG] Calculated length (from start to end address): {}".format(calcLenAsNum) )
            print( r"[DEBUG] Rounded dump length: {} / 0x{}".format(dumpLenAsNum, dumpLen) )

        # TODO/FIXME: if dump length is bigger than 64 kBytes, it needs to be broken into chunks of 64 kB or less
        if dumpLenAsNum > 65536:
            print( "[ERROR] Currently only dumps up to 64 kBytes are supported." )
            return False

        dumpLen = dumpLen.encode('ascii')

        # add output file parameter if filepath is given
        if filepath:
            proc = subprocess.run(["sg_raw", "-r", str(dumpLenAsNum), "-o", filepath, self.scsidev, "F1", "7F", "00", "00", "00", addr[6:8], addr[4:6], addr[2:4], addr[0:2], dumpLen[6:8], dumpLen[4:6], dumpLen[2:4], dumpLen[0:2], "88", "00", "00"], check=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE, universal_newlines=True)
        else:
            proc = subprocess.run(["sg_raw", "-r", str(dumpLenAsNum), self.scsidev, "F1", "7F", "00", "00", "00", addr[6:8], addr[4:6], addr[2:4], addr[0:2], dumpLen[6:8], dumpLen[4:6], dumpLen[2:4], dumpLen[0:2], "88", "00", "00"], check=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE, universal_newlines=True)

        if verbose:
            print( r"[DEBUG] proc: {}".format(proc) )

        # check expected output message dependent on if dump goes into a file or not
        if filepath:
            expectedMsg = str.format("Writing {} bytes of data to ", dumpLenAsNum)
        else:
            expectedMsg = str.format("Received {} bytes of data", dumpLenAsNum)

        if proc.returncode == 0 and proc.stdout == '' and ("SCSI Status: Good" in proc.stderr) and (expectedMsg in proc.stderr):
            print( r"[INFO] {}".format(proc.stderr) )
            return True
        else:
            print( r"[ERROR] Raw SCSI command did not work as expected. (proc: {})".format(proc) )
            return False

    def setvalue(self, address, value, verbose=True):
        '''Generic implementaiton of the setvalue command
         
        Execute setvalue command via serial or SCSI.
        '''
        
        address = address.lower()
        value = value.lower()

        if verbose:
            print(r"[DEBUG] setvalue value 0x{} at address 0x{}".format(value, address) )

        addressAsNum = int(address, 16)
        if addressAsNum % 4 != 0:
            print( "[ERROR] Address must be aligned but it's not." )
            return False

        if self.validScsiDev:
            ret = self.setvalue_scsi(address, value, verbose)
        else:
            ret = self.setvalue_serial(address, value, verbose)
        return ret

    def setvalue_serial(self, address, value, verbose=True):
        '''Implementation of the setvalue command (via serial)'''

        if not self.validSerialDev:
            print( r"[ERROR] No valid serial device." )
            return False

        cmd = b'setvalue\r'
        if not self.trx_line(cmd):
            return False

        if not self.rx_check_expected(b'Input addr(0xfffffff0):'):
            return False

        addr = address.encode('ascii') + b'\r'
        if not self.trx_line(addr):
            return False

        if not self.rx_check_expected(b'Input value(0xfffffff0):'):
            return False

        val = value.encode('ascii') + b'\r'
        if not self.trx_line(val):
            return False

        # concatenate expected result
        readbackMemory = b'Addr 0x' + address.encode('ascii') + b' value :0x' + value.encode('ascii') + b'\n'
        if not self.rx_check_expected(readbackMemory):
            return False
        
        if not self.rx_check_expected(self.prompt):
            return False
        
        return True

    def setvalue_scsi(self, address, verbose=True, readAfterGo=True):
        '''Implementation of the setvalue command (via SCSI)'''
        
        if not self.validScsiDev:
            print( r"[ERROR] No valid SCSI device." )
            return False

        addr = address.encode('ascii')
        val = value.encode('ascii')
        proc = subprocess.run(["sg_raw", "-r", "64", self.scsidev, "F1", "1F", "00", "00", "00", addr[6:8], addr[4:6], addr[2:4], addr[0:2], val[6:8], val[4:6], val[2:4], val[0:2]], check=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE, universal_newlines=True)

        if verbose:
            print( r"[DEBUG] proc: {}".format(proc) )

        if proc.returncode == 0 and proc.stdout == '' and ("SCSI Status: Good" in proc.stderr) and ("No data received" in proc.stderr):
            return True
        else:
            return False

    def go(self, address, verbose=True, readAfterGo=True):
        '''Generic implementation of the go command
         
        Execute go command via serial or SCSI.
        '''
        
        address = address.lower()

        if verbose:
            print(r"[DEBUG] go to address 0x{}".format(address) )

        if self.validScsiDev:
            ret = self.go_scsi(address, verbose, readAfterGo)
        else:
            ret = self.go_serial(address, verbose, readAfterGo)
        return ret

    def go_serial(self, address, verbose=True, readAfterGo=True):
        '''Implementation of the go command (via serial)'''
        
        if not self.validSerialDev:
            print( r"[ERROR] No valid serial device." )
            return False
        
        cmd = b'go\r'
        if not self.trx_line(cmd):
            return False

        if not self.rx_check_expected(b'Input addr(0x08000000):'):
            return False

        addr = address.encode('ascii') + b'\r'
        if not self.trx_line(addr):
            return False

        if readAfterGo:
            self.readline(verbose=True)

        return True

    def go_scsi(self, address, verbose=True, readAfterGo=True):
        '''Implementation of the go command (via SCSI)'''
        
        if not self.validScsiDev:
            print( r"[ERROR] No valid SCSI device." )
            return False

        addr = address.encode('ascii')
        proc = subprocess.run(["sg_raw", "-r", "64", self.scsidev, "F1", "9F", "00", "00", "00", addr[6:8], addr[4:6], addr[2:4], addr[0:2]], check=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE, universal_newlines=True)

        if verbose:
            print( r"[DEBUG] proc: {}".format(proc) )

        if proc.stdout == '' and ("SCSI Status: Good" in proc.stderr) and ("No data received" in proc.stderr):
            return True
        else:
            return False

    def download(self, address, filepath, verbose=True):
        '''Implementations of the download command'''
        
        if verbose:
            print(r"[DEBUG] download to address 0x{}".format(address) )

        if self.validScsiDev:
            ret = self.download_scsi(address, filepath, verbose)
        else:
            ret = self.download_serial(address, filepath, verbose)
        return ret

    def download_serial(self, address, filepath, verbose=True):
        '''Implementation of the download command (via serial)'''
        
        if not self.validSerialDev:
            print( r"[ERROR] No valid serial device." )
            return False

        cmd = b'download\r'
        if not self.trx_line(cmd):
            return False
        
        if not self.rx_check_expected(b'Input down addr(0x08000000):'):
            return False
        
        txAddress = address.encode('ascii')
        if not self.trx_line( txAddress + b'\r' ):
            return False

        if not self.rx_check_expected( b'addr :0x' + txAddress + b'\nSelect your file:' ):
            return False

        with open(filepath, "rb") as fp:
            data = fp.read()

            payloadLen = len(data)
            downloadLen = 6 + payloadLen # 4 bytes length + 2 bytes checksum + length of payload data
            #if verbose:
            print( r"[DEBUG] payload length: {}, overall download length: {}".format( payloadLen, downloadLen ) )

            try:
                txDownloadLen = downloadLen.to_bytes(4, byteorder='little')
            except:
                print( "[ERROR] Unable to convert length to 16 bit value to be transmitted." )
                return False

            # transmit the size
            if not self.trx_line(txDownloadLen, rxEcho=False):
                return False

            # transmit the payload data
            if not self.trx_line(data, rxEcho=False):
                return False

            # calculate the checksum (16 bit)
            checkSum = sum(data)
            checkSum16Bits = checkSum % (2**16)

            if verbose:
                print( r"[DEBUG] checkSum={}, checkSum16Bits={}".format( checkSum, checkSum16Bits ) )

            try:
                txCheckSum = checkSum16Bits.to_bytes(2, byteorder='little')
            except Exception as ex:
                print( r'[ERROR] Unable to calculate checksum ("{}", value: {}).'.format(ex, checkSum16Bits) )
                return False
            if verbose:
                print( r"[DEBUG] checkSum={}, txCheckSum={}".format( checkSum, txCheckSum ) )

            # transmit the calculated checksum
            if not self.trx_line(txCheckSum, rxEcho=False):
                return False

            if not self.rx_check_expected(b'Strat check, Wait...'):
                return False

            self.readline(verbose=verbose) # read checksum line, TODO: compare returned checksum

            if not self.rx_check_expected(b'Down OK!\n'):
                return False

            if not self.rx_check_expected(self.prompt):
                return False

            return True

    def download_scsi(self, address, filepath, verbose=True):
        '''Implementation of the download command (via SCSI)'''
        
        if not self.validScsiDev:
            print( r"[ERROR] No valid SCSI device." )
            return False

        with open(filepath, "rb") as fp:
            data = fp.read()

        payloadLen = len(data)
        addressAsNum = int(address, 16)
        nXferChunks = math.ceil( payloadLen/4096 )

        if verbose:
            print( r"[DEBUG] payloadLen: {}".format(payloadLen) )
            print( r"[DEBUG] Calculated number of transfer chunks: {}".format( nXferChunks ) )

        # write file in chunks of up to 4096 bytes
        # TODO: data chunks are stored in temporary file: specify file name?
        nRemainingLen = payloadLen
        nChunkIdx = 0
        while nRemainingLen > 0:
            if nRemainingLen > 4096:
                nXferLen = 4096
            else:
                nXferLen = nRemainingLen
            
            address = "{:08x}".format( addressAsNum )
            addr = address.encode('ascii')
            downloadLen = ("{:08x}".format( nXferLen )).encode('ascii')
            if verbose:
                print( r"[DEBUG] Address and transfer length of chunk #{}: 0x{:08x}, len: {}".format( nChunkIdx, addressAsNum, nXferLen ) )

            with open("tmp.bin", "wb") as fp:
                fp.write(data[ nChunkIdx*4096 : nChunkIdx*4096+nXferLen ])

            proc = subprocess.run(["sg_raw", "-s", str.format("{}", nXferLen), "-i", "tmp.bin", self.scsidev, "F1", "3F", "00", "00", "00", addr[6:8], addr[4:6], addr[2:4], addr[0:2], downloadLen[6:8], downloadLen[4:6], downloadLen[2:4], downloadLen[0:2], "68", "00", "00" ], check=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE, universal_newlines=True)
            if verbose:
                print( r"[DEBUG] proc: {}".format(proc) )

            if not (proc.returncode == 0 and proc.stdout == '' and ("SCSI Status: Good" in proc.stderr)):
                return False

            nChunkIdx = nChunkIdx + 1
            nRemainingLen = nRemainingLen - nXferLen
            addressAsNum = addressAsNum + nXferLen

        # finish the download
        proc = subprocess.run(["sg_raw", "-r", "64", self.scsidev, "F1", "3C", "00", "00", "00", "00"], check=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE, universal_newlines=True)
        if verbose:
            print( r"[DEBUG] proc: {}".format(proc) )

        # TODO: delete temporary file after completion of download or on error
        # TODO: optionally also read the data from the serial interface

        if proc.returncode == 0 and proc.stdout == '' and ("SCSI Status: Good" in proc.stderr) and ("No data received" in proc.stderr):
            return True
        else:
            return False

    def load_binfile(self, startAddr, filepath, verbose=True):
        '''Load contents of a binary file to specific memory region on the target based on the native "download" command'''
        
        address = startAddr
        addressAsNum = int(startAddr, 16)
        
        if addressAsNum % 4 != 0:
            print( "[ERROR] Address must be aligned but it's not." )
            return False

        # TODO: add progress bar; calculation of estimated remaining time

        if verbose:
            print( r"[DEBUG] load_binfile('{}' at 0x{:08x})".format(filepath, addressAsNum) )

        statinfo = os.stat(filepath)
        alignment = statinfo.st_size%4
        if verbose:
            print( r"[DEBUG] File size: {}".format(statinfo.st_size) )

        if not self.download(address, filepath, verbose):
            print("[ERROR] Download failed.")
            return False

        return True

    def rx_byte(self, verbose=True):
        '''Receive a single byte/character from the serial (but do not have a look at the content and do not return it)'''
        
        if not self.validSerialDev:
            print( r"[ERROR] No valid serial device." )
            return False
                
        cRx = self.ser.read(1)

        if verbose:
            print(r"[INFO] Rx: {}".format( cRx ))

        if cRx == b'':
            return False
        else:
            return True

    def tx_byte(self, value, verbose=True):
        '''Receive a single byte/character from the serial'''
        
        if not self.validSerialDev:
            print( r"[ERROR] No valid serial device." )
            return False

        cTx = value.encode('ascii')

        if verbose:
            print(r"[INFO] Tx: {}".format( cTx ))

        if self.ser.write(cTx):
            return True
        else:
            return False


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='%(prog)s')

    parser.add_argument('-p', action="store", default=False, 
                    dest='serport',
                    help="serial device port name (e.g. '/dev/ttyUSB0' or 'COM1')")

    parser.add_argument('-s', action="store", default=False, 
                    dest='scsidev',
                    help="generic SCSI device file name (e.g. '/dev/sg2')")

    parser.add_argument('-c', action="store", default=False,
                    required=True,
                    dest='command',
                    help='command (dump, setval[ue], go, load, exec, txb, rxb, trxb, txbrxl)')

    parser.add_argument('-a', action="store", default=False,
                    required=True,
                    dest='address',
                    help="start address as hex string, without '0x' prefix")

    parser.add_argument('-e', action="store", default=False,
                    dest='endAddress',
                    help="end address as hex string, without '0x' prefix")

    parser.add_argument('-n', action="store", default=False,
                    dest='value',
                    help="value to be set in setval[ue] command, as hex string, without '0x' prefix")

    parser.add_argument('-b', action="store", default=False,
                    dest='txbyte',
                    help='byte to be transmitted in txb command')

    parser.add_argument('-f', action="store", default=False,
                    dest='file',
                    help='path to a binary file')

    parser.add_argument('-v', action="store", default=False,
                    dest='verbosity',
                    help='print detailed output')

    parser.add_argument('--version', action='version',
                        version='%(prog)s 0.3')

    args = parser.parse_args()
    #print(args) # for debugging purpose

    cmd = args.command.lower()
    address = "{:08x}".format( int(args.address, 16) )
    
    if args.endAddress:
        endAddress = "{:08x}".format( int(args.endAddress, 16) )
    else:
        endAddress = address # set end address equal to start address if no end address is given

    if args.value:
        value = "{:08x}".format( int(args.value, 16) )
    
    fname = None
    verbose = args.verbosity

    platformType = platform.system()
    if verbose:
        print( r"[DEBUG] Platform: {}".format( platformType ) )
    if platformType != "Linux":
        print( "[WARNING] Not run under Linux. SCIS commands won't be supported on this platform." )

    if not args.serport:
        if cmd in ['txb', 'rxb', 'trxb', 'txbrxl', 'rxl']:
            print( r"[ERROR] Command '{}' needs a serial (-p) device.".format(cmd) )
            sys.exit(13)
        if not args.scsidev:
            print( "[ERROR] At least a serial (-p) or an SCSI device (-s) needs to be given." )
            sys.exit(14)

    if args.file:
        # check if the file exists when it is going to be loaded (and optionally also executed)
        if cmd == 'load' or cmd == 'exec':
            if os.path.isfile(args.file):
                if verbose:
                    print(r"[DEBUG] File '{}' exists.".format(args.file))
                fname = args.file
            else:
                print(r"[ERROR] File '{}' does not exist.".format(args.file))
                sys.exit(12)
        else:
            fname = args.file

    try:
        inst = snowbirdopter(serport=args.serport, scsidev=args.scsidev, verbose=verbose)

        if cmd == 'go':
            if inst.go(address, verbose):
                if verbose:
                    print("[INFO] Go command probably succeeded.")
            else:
                print("[ERROR] Go command failed.")
                sys.exit(1)

        elif cmd == 'dump':
            if inst.dump(address, endAddress, fname, verbose):
                if verbose:
                    print("[INFO] Dump succeeded.")
            else:
                print("[ERROR] Dump failed.")
                # sys.exit(2) # FIXME

        elif cmd == 'setvalue' or cmd == 'setval':
            if inst.setvalue(address, value, verbose):
                if verbose:
                    print("[INFO] Setting value succeeded.")
            else:
                print("[ERROR] Setting value failed.")
                sys.exit(3)

        elif cmd == 'load' or cmd == 'exec': # load data/code (and eventually also execute code)
            if inst.load_binfile(address, fname, verbose):
                print("[INFO] Loading binfile succeeded.")
                if cmd == 'exec':
                    if inst.go(address):
                        if verbose:
                            print("[INFO] Executing binfile succeeded.")
                    else:
                        print("[ERROR] Executing binfile failed.")
            else:
                print("[ERROR] Loading binfile failed.")
                sys.exit(4)

        elif cmd == 'txb': # transmit byte
            if inst.tx_byte(args.txbyte, verbose):
                if verbose:
                    print("[INFO] Sending byte succeeded.")
            else:
                print("[ERROR] Sending byte failed.")
                sys.exit(5)

        elif cmd == 'rxb': # receive byte
            if inst.rx_byte():
                print("[INFO] Receiving byte succeeded.")
            else:
                print("[ERROR] Receiving byte failed.")
                sys.exit(6)

        elif cmd == 'trxb': # transmit byte and immediately receive byte
            if inst.tx_byte(args.txbyte, verbose):
                if inst.rx_byte():
                    if verbose:
                        print("[INFO] Transceiving byte succeeded.")
                else:
                    print("[ERROR] Transceiving byte failed.")
                    sys.exit(7)
            else:
                print("[ERROR] Transceiving byte failed.")
                sys.exit(8)

        elif cmd == 'txbrxl': # transmit byte and receive line
            nLines = 1        
            if args.value:
                nLines = int(args.value)
            if inst.tx_byte(args.txbyte, verbose):
                for k in range(0, nLines):
                    if not inst.readline(verbose=verbose):
                        print("[ERROR] Transceiving byte failed.")
                        sys.exit(8)
                if verbose:
                    print("[INFO] Transceiving byte succeeded.")    
            else:
                print("[ERROR] Transceiving byte failed.")
                sys.exit(9)

        elif cmd == 'rxl': # receive line(s), without any transmit
            nLines = 1        
            if args.value:
                nLines = int(args.value)
            for k in range(0, nLines):
                if not inst.readline(verbose=verbose):
                    print("[ERROR] Receiving line(s) failed.")
                    sys.exit(10)
            if verbose:
                print("[INFO] Receiving line(s) succeeded.")    

        else:
            print(r"[ERROR] Unrecognized command.")
            sys.exit(11)

        sys.exit(0)

    except Exception as ex:
        trace_back = sys.exc_info()[2]
        line = trace_back.tb_lineno
        #raise ex # uncomment line to allow further debugging
        print( r'[ERROR] Internal error occured. Exception: "{}" on line: {}.'.format(ex, line) )

        sys.exit(99)

