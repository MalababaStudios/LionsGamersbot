import grpc
import bot_tokens

import wakeful_action_pb2
import wakeful_action_pb2_grpc

with open('lionsgamersbot.crt', 'rb') as f:
    client_cert = f.read()
with open('lionsgamersbot.key', 'rb') as f:
    client_key = f.read()
with open('ca.crt', 'rb') as f:
    trusted_certs = f.read()

def wakeup() -> bool:


    target = bot_tokens.WAKEFUL_ACTION_HOST
    credentials = grpc.ssl_channel_credentials(
        root_certificates=trusted_certs,
        private_key=client_key,
        certificate_chain=client_cert
    )

    try:
        with grpc.secure_channel(target, credentials) as channel:
            stub = wakeful_action_pb2_grpc.WakefulServiceStub(channel)
            response = stub.WakeUp(wakeful_action_pb2.WakeRequest())
            return response.success
    except Exception e:
        print(f"Error while sending wakeup call: {e}")
        return False

