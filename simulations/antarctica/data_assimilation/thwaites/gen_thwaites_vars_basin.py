from cslvr import *
from fenics  import *
import timeit
import sys
start=timeit.default_timer()

out_dir  = 'dump/vars_thwaites_basin/'
thklim   = 1.0
measures = DataFactory.get_ant_measures(res=900)
bedmap1  = DataFactory.get_bedmap1(thklim=thklim)
bedmap2  = DataFactory.get_bedmap2(thklim=thklim)

mesh = Mesh('dump/meshes/thwaites_3D_U_mesh_basin.xml.gz')

dm = DataInput(measures, mesh=mesh)
d1 = DataInput(bedmap1,  mesh=mesh)
d2 = DataInput(bedmap2,  mesh=mesh)

S     = d2.get_expression("S",        near=False)
B     = d2.get_expression("B",        near=False)
M     = d2.get_expression("mask",     near=True)
L     = d2.get_expression('lat_mask', near=True)
adot  = d1.get_expression("acca",     near=False)
T_s   = d1.get_expression("temp",     near=False)
q_geo = d1.get_expression("ghfsr",    near=False)
u_ob  = dm.get_expression("vx",       near=False)
v_ob  = dm.get_expression("vy",       near=False)
U_msk = dm.get_expression("mask",     near=True)

model = D3Model(mesh=mesh, out_dir=out_dir, save_state=True)
model.deform_mesh_to_geometry(S, B)
model.calculate_boundaries(mask=M, lat_mask=L, U_mask=U_msk, adot=adot, 
                           mark_divide=True)

model.init_T_surface(T_s)
model.init_q_geo(q_geo)
model.init_U_ob(u_ob, v_ob)

model.save_xdmf(model.ff,   'ff')
model.save_xdmf(model.U_ob, 'U_ob')
model.state.close()

elapsed=timeit.default_timer() - start
elapsed=elapsed/60.
print 'It took %f minutes to run %s' % (elapsed, sys.argv[0])

