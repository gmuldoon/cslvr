#!/bin/bash

#cd to directory with Thwaites scripts
cd /home/gailm/Software/myfork_cslvr/simulations/antarctica/data_assimilation/thwaites

#make archive directory if it doesn't already exist
mkdir -p ./archive

#if output files already exist, move them to archive with timestamp in filename
for FILE in `ls *.o`; do
    mod=$(stat -c%y $FILE)
    mod=$( echo "$mod" |cut -c12-19)
    FILE2=$FILE-$mod
    mv $FILE ./archive/$FILE2
    echo "$FILE archived" 
done

#create a list of the scripts to run in proper order
declare -a scripts=("gen_thwaites_mesh_basin.py" \
		    "gen_thwaites_vars_basin.py" \
		    "gen_submeshes_basin.py" \
		    "data_assimilation.py")
declare -a outfiles=("thwaites_mesh_basin.o" \
			 "thwaites_vars_basin.o" \
			 "submeshes_basin.o" \
			 "data_assimilation.o")
declare -a mins=("10" "60" "5" "m")

#run and time each script
#for s in $(seq 1 ${#scripts[@]); do
for s in $(seq 3 4); do
    echo "Running ${scripts[s-1]}."
    echo "This will take ~${mins[s-1]} minutes."
    start=$(date +%s)
    python ${scripts[s-1]} &> ${outfiles[s-1]}
    end=$(date +%s)
    runtime=$(($((end-start))/60))
    echo "This script took $runtime minutes to finish."
done

#mpirun -n 2 python gen_thwaites_mesh_basin.py &> thwaites_mesh_basin.o
#mpirun -n 2 python gen_submeshes_basin.py &> submeshes_basin.o
#mpirun -n 2 python gen_thwaites_vars_basin.py &> thwaites_vars_basins.o
#mpirun -n 2 python data_assimilation.py &> data_assimilation.o

