from config import socketio
from flask_socketio import join_room, Namespace, emit, leave_room
import uuid

class SocketHandler(Namespace):
    
    
    def on_connect(self):
        sid = str(uuid.uuid4())
        print(sid)
        join_room(sid)
        socketio.emit('auth',{'sid':sid},room=sid)
        print('Client connecter')

    
    def on_disconnect(self):
        print('disconnected')
