#!/bin/bash

#cd to directory with Thwaites scripts
cd /home/gailm/Software/cslvr/simulations/antarctica/data_assimilation/thwaites

#make archive directory if it doesn't already exist
mkdir -p ./archive

#if output files already exist, move them to archive with timestamp in filename
for FILE in `ls *.o`
do
    mod=$(stat -c%y $FILE)
    mod=$( echo "$mod" |cut -c12-19)
    FILE2=$FILE-$mod
    mv $FILE ./archive/$FILE2
    echo "$FILE archived" 
done

#mpirun -n 2 python gen_thwaites_mesh_basin.py &> thwaites_mesh_basin.o
#mpirun -n 2 python gen_submeshes_basin.py &> submeshes_basin.o
#mpirun -n 2 python gen_thwaites_vars_basin.py &> thwaites_vars_basins.o
#mpirun -n 2 python data_assimilation.py &> data_assimilation.o


echo "Running gen_thwaites_mesh_basin.py."
echo "This will take ~10 minutes."
python gen_thwaites_mesh_basin.py &> thwaites_mesh_basin.o
echo "Running gen_submesshes_basin.p.y"
echo "This will take about N minutes."
python gen_submeshes_basin.py &> submeshes_basin.o
echo "Running gen_thwaites_vars_basin.py."
echo "This will take about 60 minutes."
python gen_thwaites_vars_basin.py &> thwaites_vars_basins.o
echo "Running data_assimilation.py."
echo "This will take M minutes."
python data_assimilation.py &> data_assimilation.o
