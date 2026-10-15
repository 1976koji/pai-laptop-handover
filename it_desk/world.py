"""Original IT service desk scene with genuine rigid-body case transport.
OpenArm geometry/kinematics: Enactic Apache-2.0, pinned in prepare_robot.py.
No attachment joint or pose teleport is used for the laptop case.
"""
from pathlib import Path
import json,random,math,copy,xml.etree.ElementTree as E
import numpy as np
from scipy.spatial.transform import Rotation
from collision_mesh import positive_collision_mesh
from kinematics import Kinematics,JOINTS,origin,vector,PALM_OFFSET,trajectory,validate_support_clearance,workstation_boxes,validate_support_sweep
ROOT=Path(__file__).resolve().parent

def vals(x):return ' '.join(str(float(v)) for v in x)
def pose(t):return vals(np.r_[t[:3,3],Rotation.from_matrix(t[:3,:3]).as_euler('xyz')])
def mat(color):return f'<material><ambient>{color}</ambient><diffuse>{color}</diffuse></material>'
def box(name,xyz,size,color,collide=True,friction=1.):
    geom=f'<geometry><box><size>{size}</size></box></geometry>'
    return f'<visual name="{name}"><pose>{xyz} 0 0 0</pose>{geom}{mat(color)}</visual>'+(f'<collision name="{name}"><pose>{xyz} 0 0 0</pose>{geom}<surface><friction><ode><mu>{friction}</mu><mu2>{friction}</mu2></ode></friction></surface></collision>' if collide else '')
def static(name,body):return f'<model name="{name}"><static>true</static><link name="body">{body}</link></model>'
def poses():return '<plugin filename="gz-sim-pose-publisher-system" name="gz::sim::systems::PosePublisher"><publish_link_pose>false</publish_link_pose><publish_model_pose>true</publish_model_pose><use_pose_vector_msg>true</use_pose_vector_msg><update_frequency>20</update_frequency></plugin>'

def robot_sdf(initial_q=None):
    initial_q=np.zeros(14) if initial_q is None else np.asarray(initial_q,dtype=float)
    urdf=E.parse(ROOT/'openarm.urdf').getroot();transforms={'world':np.eye(4)}
    joints=[j for j in urdf.findall('joint') if 'finger' not in j.get('name') and 'grasp' not in j.get('name')]
    for j in joints:
        t=transforms[j.find('parent').get('link')]@origin(j.find('origin'))
        if j.get('name') in JOINTS:
            r=np.eye(4);r[:3,:3]=Rotation.from_rotvec(vector(j.find('axis').get('xyz'))*initial_q[JOINTS.index(j.get('name'))]).as_matrix();t=t@r
        transforms[j.find('child').get('link')]=t
    s='<model name="openarm_it"><pose>0 0 .4 0 0 0</pose><self_collide>false</self_collide>'
    def convert_geom(g,collision=False):
        g=copy.deepcopy(g)
        for mesh in g.findall('mesh'):
            filename=mesh.attrib.pop('filename');scale=mesh.attrib.pop('scale','1 1 1')
            path=ROOT/'robot_assets'/filename.removeprefix('package://openarm_description/')
            if collision:
                path,baked_scale=positive_collision_mesh(path,vector(scale),ROOT/'collision_cache')
                scale=vals(baked_scale)
            E.SubElement(mesh,'uri').text='file://'+str(path)
            E.SubElement(mesh,'scale').text=scale
        return E.tostring(g,encoding='unicode')
    for link in urdf.findall('link'):
        name=link.get('name')
        if name=='world' or name not in transforms:continue
        s+=f'<link name="{name}"><pose>{pose(transforms[name])}</pose><gravity>false</gravity>'
        inert=link.find('inertial')
        if inert is not None:
            s+='<inertial><pose>'+pose(origin(inert.find('origin')))+'</pose><mass>'+inert.find('mass').get('value')+'</mass><inertia>'
            for key,value in inert.find('inertia').attrib.items():s+=f'<{key}>{value}</{key}>'
            s+='</inertia></inertial>'
        else:s+='<inertial><mass>.1</mass><inertia><ixx>.001</ixx><iyy>.001</iyy><izz>.001</izz></inertia></inertial>'
        for tag in ('visual','collision'):
            if name.endswith('ee_base_link'):continue  # custom complete tool replaces pinch-gripper housing
            for i,g in enumerate(link.findall(tag)):
                s+=f'<{tag} name="{tag}_{i}"><pose>{pose(origin(g.find("origin")))}</pose>'+convert_geom(g.find('geometry'),collision=(tag=='collision'))+('</'+tag+'>')
        if name.endswith('ee_base_link'):
            # Fingers replaced by custom flat rubberized supports. At target wrist
            # orientation Ry(-pi/2), the local X thickness is vertical in world.
            s+=box('tool_mount','0 0 -.01','.045 .065 .035','0.25 0.28 0.32 1')
            s+=box('support',vals(PALM_OFFSET),'.015 .075 .34','0.04 0.16 0.20 1')
        s+='</link>'
    for j in joints:
        name=j.get('name');child=j.find('child').get('link');parent=j.find('parent').get('link');typ=j.get('type')
        s+=f'<joint name="{name}" type="{typ}"><pose relative_to="{child}">0 0 0 0 0 0</pose><parent>{parent}</parent><child>{child}</child>'
        if typ=='revolute':
            lim=j.find('limit');offset=initial_q[JOINTS.index(name)];s+=f'<axis><xyz>{j.find("axis").get("xyz")}</xyz><limit><lower>{float(lim.get("lower"))-offset}</lower><upper>{float(lim.get("upper"))-offset}</upper><effort>{lim.get("effort")}</effort><velocity>.3</velocity></limit><dynamics><damping>.5</damping></dynamics></axis>'
        s+='</joint>'
        if name in JOINTS:
            s+=f'<plugin filename="gz-sim-joint-position-controller-system" name="gz::sim::systems::JointPositionController"><joint_name>{name}</joint_name><topic>/it/cmd/{name}</topic><use_velocity_commands>true</use_velocity_commands><cmd_max>.3</cmd_max><cmd_min>-.3</cmd_min><initial_position>0</initial_position></plugin>'
    s+='<plugin filename="gz-sim-joint-state-publisher-system" name="gz::sim::systems::JointStatePublisher"><topic>/it/joints</topic></plugin></model>'
    return s

def world(seed=0,target='developer'):
    rng=random.Random(seed)
    source=[.30+rng.uniform(-.006,.006),-.15+rng.uniform(-.006,.006),.90]
    dest=[.30,.15,.90]
    kin=Kinematics(ROOT/'openarm.urdf');plan=trajectory(kin,source,dest)
    clearance=validate_support_clearance(plan,source,dest)
    initial_q=np.array(plan[0]['q'])
    sweep=validate_support_sweep(kin,plan,source,dest,initial_q)
    layout={'implementation_version':'IT-1.10','initial_joint_positions':initial_q.tolist(),'start_condition':'arms initialized beside the stationary case; no home-to-case approach; simulator joints use offsets','support_sweep_check':sweep,'support_waypoint_clearance_m':clearance,'source':source,'destination':dest,'target':target,'asset_id':'SIM-DEV-001' if target=='developer' else 'SIM-STD-001','request_id':f'R-{seed:04d}','joint_plan':plan,'inventory_selection':'one matching available case per trial; no multi-SKU visual classification'}
    s='''<?xml version="1.0"?><sdf version="1.9"><world name="it_desk"><physics name="physics" type="ignored"><max_step_size>.001</max_step_size><real_time_factor>1</real_time_factor></physics><gravity>0 0 -9.81</gravity>
    <plugin filename="gz-sim-physics-system" name="gz::sim::systems::Physics"/><plugin filename="gz-sim-user-commands-system" name="gz::sim::systems::UserCommands"/><plugin filename="gz-sim-scene-broadcaster-system" name="gz::sim::systems::SceneBroadcaster"/><plugin filename="gz-sim-sensors-system" name="gz::sim::systems::Sensors"><render_engine>ogre2</render_engine></plugin>
    <scene><ambient>.7 .7 .7 1</ambient><background>.12 .16 .20 1</background><shadows>false</shadows></scene><light name="office" type="directional"><pose>0 0 3 0 0 0</pose><diffuse>.9 .9 .9 1</diffuse><direction>-.3 .2 -1</direction></light>'''
    s+=static('floor',box('floor','0 0 -.04','4 4 .08','.60 .64 .68 1'))
    pedestal_boxes=[('base',[-.30,0,.10],[.30,.34,.20]),('rear_column',[-.30,0,.65],[.08,.12,.90]),('mount_beam',[-.15,0,1.06],[.30,.04,.08])]
    s+=static('pedestal',''.join(box(name,vals(c),vals(size),'.10 .12 .16 1') for name,c,size in pedestal_boxes))
    # Narrow support surfaces leave space for both adapters under the case edges.
    for name,p,color in [('inventory_shelf',source,'.14 .30 .50 1'),('handover_counter',dest,'.12 .54 .36 1')]:
        x,y,z=p
        s+=static(name,''.join(box(part,vals(center),vals(size),color) for part,center,size in workstation_boxes(p)))
    s+=static('back_wall',box('wall','-.40 0 1.05','.06 1.8 2.1','.75 .80 .83 1'))
    s+=static('service_display',box('screen','-.15 .52 1.1','.04 .32 .22','.04 .12 .20 1',False))
    x,y,z=source;color='.11 .13 .16 1'
    s+=f'<model name="laptop_case"><pose>{x} {y} {z} 0 0 0</pose><link name="case"><inertial><mass>1.2</mass><inertia><ixx>.008</ixx><iyy>.010</iyy><izz>.016</izz></inertia></inertial>'
    s+=box('case','0 0 0','.30 .29 .04',color)+box('lid_seam','0 0 .022','.277 .255 .006','.02 .025 .03 1',False)+box('closed_laptop','0 0 .027','.27 .248 .006','.72 .74 .77 1',False)+box('hinge','-.136 0 .025','.010 .235 .012','.20 .22 .25 1',False)+box('front_edge','.137 0 .020','.003 .23 .003','.45 .47 .50 1',False)+box('asset_label','.090 .080 .0305','.040 .020 .001','.93 .94 .95 1',False)+'</link>'+poses()+'</model>'
    # Check the actual hanging-tool geometry against the pedestal at startup.
    for side in ('left','right'):
        t=kin.frame(side,initial_q);c=t[:3,3]
        h=np.abs(t[:3,:3])@np.array([.0075,.0375,.17])
        for name,pc,size in pedestal_boxes:
            pc=np.array(pc);ph=np.array(size)/2
            overlap=np.minimum(c+h,pc+ph)-np.maximum(c-h,pc-ph)
            if np.all(overlap>0):raise RuntimeError('Initial tool overlaps pedestal: '+side+'/'+name)
    layout['initial_support_pedestal_check']='passed'
    s+=robot_sdf(initial_q)
    for name,pos,look,size in [('front',np.array([1.7,-1.5,1.60]),np.array([.18,0,.78]),(640,480)),('overhead',np.array([.30,0,2.1]),np.array([.30,0,.80]),(320,240))]:
        d=look-pos;yaw=math.atan2(d[1],d[0]);pitch=math.atan2(-d[2],np.linalg.norm(d[:2]));w,h=size
        s+=f'<model name="camera_{name}"><static>true</static><pose>{vals(pos)} 0 {pitch} {yaw}</pose><link name="camera"><sensor name="rgb" type="camera"><always_on>true</always_on><update_rate>5</update_rate><topic>/it/{name}</topic><camera><horizontal_fov>.9</horizontal_fov><image><width>{w}</width><height>{h}</height><format>R8G8B8</format></image><clip><near>.02</near><far>10</far></clip></camera></sensor></link></model>'
    s+='</world></sdf>';E.fromstring(s);return s,layout
