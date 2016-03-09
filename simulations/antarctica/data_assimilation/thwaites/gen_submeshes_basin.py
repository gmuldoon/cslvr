from cslvr import *

# set the output directory :
in_dir  = 'dump/vars_thwaites_basin/'
out_dir = in_dir

f  = HDF5File(mpi_comm_world(), in_dir + 'state.h5',     'r')
fn = HDF5File(mpi_comm_world(), in_dir + 'submeshes.h5', 'w')

model = D3Model(mesh=f, out_dir=out_dir)
      
model.init_lat_mask(f)

#Forming the meshes
model.form_bed_mesh()
model.form_srf_mesh()
model.form_dvd_mesh()

#Saving the meshes
#Parallel to gen_submeshes.py from jakobshavn case
model.save_bed_mesh(fn)
model.save_srf_mesh(fn)
model.save_dvd_mesh(fn)

fn.close()
