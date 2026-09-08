# Hypergiant ISP Joint Optimization
Code for "On the Benefits of Joint Optimization of Reconfigurable CDN-ISP Infrastructure" by Zerwas et al. (2021)
[(IEEExplore)](https://ieeexplore.ieee.org/abstract/document/9566292)

## Folder structure

- `docker`: Docker-related files 
- `scripts`: Python scripts for experiments and evaluation
- `src`: Python source



## Preparation

### Docker
- Download CPLEX and put the archive into ```docker```. Build the image
```bash
docker-compose build -f docker/docker-compose.yml .
```
- Start the container (or use via PyCharm/VS Code/...):
```bash
docker run -it -v $(pwd)/data:/home/sim/data  hypergiant-isp-topology-optimization bash
```

### Manual - Install Dependencies

#### Python:
- Tested with Python 3.7.
```bash
pip install networkx numpy pandas tables matplotlib statsmodels scipy
```

#### SCIP for usage with or-tools
- Download **SCIP Optimization Suite** (https://scipopt.org/index.php#download) 
- Extract and on the top-level of the extracted folder execute the following commands:
    ```bash
    mkdir build
    cd build
    cmake -DCMAKE_INSTALL_PREFIX=scip/install/dir -DGMP=false -DZIMPL=false -DTPI=tny -DPARASCIP=true ..
    make
    make install
    ```

#### GLPK (optional)
- Download GLPK
- Extract, change into folder and execute:
    ```bash
    ./configure --prefix=<install_path> --with-pic
    make
    make install
    ```

#### Gurobi (optional)
- See the Gurobi Website. Basically download and extract a folder.

#### CPLEX (optional)
- Download and install from (https://www.ibm.com/academic/technology/data-science)

#### OR-Tools
- Clone repository: 
    ```bash
    git clone https://github.com/google/or-tools
    ```
- Checkout the tag v7.3
- Go to directory and execute `make third_party`. This will create Makefile.local
- Edit Makefile.local:
  - Check Python version
  - UNIX_SCIP_DIR=scip/install/dir
  - Add the lines for Gurobi 
  - Add the line for CPLEX
- In makefiles/Makefile.unix.mk set SCIP_LNK to
    ```bash
    -Wl,-rpath $(UNIX_SCIP_DIR)/lib -L$(UNIX_SCIP_DIR)/lib -m64 -lc -ldl -lm -lpthread -lscip
    ```
- Compile and test
    ```bash
    make python && make test_python
    ```
- Finally, install:
    ```
    make install_python
    ```
- Before adding solvers later on, `make clean_cc` so that all libraries are built from scratch.

## Running

The folder `scripts` contains the Python scripts. To run them, first start and enter the container:
```bash
docker run -it -v $(pwd)/data:/home/sim/data  hypergiant-isp-topology-optimization bash
```
Then, switch into the folder and run the scripts as
```bash
PYTHONPATH=../src python3 short_term/run_...py
```
Note that the input data cannot be provided. Furthermore, some configuration attributes have been redacted for data
privacy reasons. Therefore, the scripts won't do anything upon execution.
However, the scripts should provide a good starting point on running the optimization on your own data.

The scripts are roughly grouped according to the structure of the evaluation in the paper (`long_term`, `short_term`,
`failure_analysis` and `randomized_demands`. Each folder contains scripts to run all optimization schemes that are 
compared.

After running the optimizations, the scripts `aggregate_raw_solutions.py` and `get_reconfiguraton_metrics.py` help to 
aggregate the data from the individual JSON files into a HDF5 file. 
Note that also here some parameters were zeroed out for data privacy reasons.

The folder `examples` contains some small scale examples and also exemplary data files to illustrate the structure.
