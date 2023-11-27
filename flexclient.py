import asyncio
import websockets
import socket
import json
from threading import Thread, Lock
import time

bPort = input("Port(Blank = 8882): ")
if(bPort == ""):
	bPort = "8882"

# Do not change
FX_PACKET_MAGIC = 0x88885846

fxsock = None
fxcommlock = Lock()
fx_net_ctrl_ver = 0

def fxReset():

	global fxsock

	if(fxsock != None):
		fxsock.close()
		fxsock = None

def sendFx(msg_content):
	if(fxsock == None):
		return False
	
	msg = FX_PACKET_MAGIC.to_bytes(length=4, byteorder='little') + len(msg_content).to_bytes(length=4, byteorder='little') + msg_content
	
	sent_size = 0
	
	while(sent_size < len(msg)):

		try:

			size = fxsock.send(msg[sent_size:])

		except TimeoutError:

			return False

		if(size == 0):
			return False
		
		sent_size+=size

	return True

def sendFxText(msg_content):
	return sendFx(msg_content.encode('utf-8'))

def sendFxJson(json_rq):
	msg_content = json.dumps(json_rq)
	return sendFxText(msg_content)

def recvFxRaw(data_size):
	if(fxsock == None):
		return None

	msg_data = bytes()

	while(len(msg_data) < data_size):

		try:

			data = fxsock.recv(data_size - len(msg_data))

		except TimeoutError:

			return None

		if(len(data) == 0):
			return None
		
		msg_data+=data

	return msg_data

def recvFx():
	if(fxsock == None):
		return None
	
	base_data = recvFxRaw(8)

	if(base_data == None or int.from_bytes(base_data[:4], byteorder='little') != FX_PACKET_MAGIC):
		return None

	return recvFxRaw(int.from_bytes(base_data[4:8], byteorder='little'))

def recvFxText():
	msg_data = recvFx()
	if(msg_data == None):
		return None
	return msg_data.decode('utf-8')

def recvFxJson():
	msg_data = recvFxText()
	if(msg_data == None):
		return None
	return json.loads(msg_data)

def fxError(web_response, error = "Connection error"):
	web_response["fx_msg_type"] = "fatal_error"
	web_response["error"] = error

def fxHandleError(fx_resp, web_response = None): # returns True if an error was detected and put in the web response

	global fxsock

	if(fx_resp == None or "fatal_error" in fx_resp or not "fx_msg_type" in fx_resp):
		if(web_response != None):
			fxError(web_response, "Connection error" if (fx_resp == None or not "fatal_error" in fx_resp) else fx_resp["fatal_error"])
		fxReset()
		return True
	
	return False

async def webhandler(websocket, path):

	global fxsock
	global fx_net_ctrl_ver

	while True:
		
		try:
			web_msg = json.loads(await websocket.recv())
		except:
			fxReset()
			return
		
		web_response = {}

		with fxcommlock:

			if(fxsock == None and web_msg["fx_msg_type"] != "login"):

				fxError(web_response)

			elif(web_msg["fx_msg_type"] == "login"):
				
				fxReset()

				time.sleep(1) # wait cuz flexlion might need a bit of time to reset the socket

				connected = False

				fxsock = socket.socket(socket.AF_INET,
								socket.SOCK_STREAM)
				fxsock.setsockopt(socket.SOL_TCP, socket.TCP_NODELAY, 1)
				fxsock.settimeout(8)
				try:
					fxsock.connect((web_msg["fx_ip"], int(web_msg["fx_port"])))
					connected = True
					print(f"Connected to target at {web_msg['fx_ip']}:{web_msg['fx_port']}, trying to log in...")
				except:
					fxError(web_response, "Failed to connect to target.")
					print("Failed to connect to target")

				if(connected):
				
					sendFxText(web_msg["fx_pwd"])
					
					fx_resp = recvFxJson()

					if(not fxHandleError(fx_resp, web_response)):

						web_response = fx_resp
						fx_net_ctrl_ver = fx_resp["fx_net_ctrl_ver"]

						print(f"Logged in, build_type = {fx_resp['build_type']}, fx_net_ctrl_ver = {fx_net_ctrl_ver}")

					else:

						print(f"Login failed, error: {web_response['error']}")
						
						fxReset()


			elif(web_msg["fx_msg_type"] in ["fx_poll", "fx_update_module_state"]):
				
				sendFxJson(web_msg)

				fx_resp = recvFxJson()

				if(not fxHandleError(fx_resp, web_response)):
					
					web_response = fx_resp

			else:

				print("Unknown msg type!")

		try:
			await websocket.send(json.dumps(web_response))
		except:
			fxReset()
			return
 
wsserver = websockets.serve(webhandler, "localhost", int(bPort))
 
asyncio.get_event_loop().run_until_complete(wsserver)
asyncio.get_event_loop().run_forever()