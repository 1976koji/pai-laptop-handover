from ros_gz_interfaces.srv import ControlWorld
request=ControlWorld.Request();request.world_control.pause=True
response=ControlWorld.Response()
assert hasattr(response,'success') and request.world_control.pause
print('ControlWorld interface available; runtime service acknowledgement will be checked per request')
