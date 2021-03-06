import itertools
import math
import os
import sys
import copy
import eigen

# This file generates multiple transpositions for benchmarking reasons.
# The generated transpositions differ in: Size, dimensionality and order.
# The permutations are choosen such that no index can be fused.
 
if len(sys.argv) < 3:
    print "usage: <number of threads> <thread affinity> <compiler>"
    print ""
    print "thread affinity:"
    print "   The thread affinity needs to specified for the given system because it can effect the performance severely."
    print "   Thes specified value respectively sets the 'KMP_AFFINITY' or 'GOMP_CPU_AFFINITY' environment variable for Intel's ICPC or g++."
    print "   Examples:"
    print "     ICPC: 'compact,1'"
    print "     g++: '0,1,2,3'"
    print ""
    print "compiler: this value can be either 'g++' or 'icpc'"
    print ""
    print "Example: 'python benchmark.py 24 compact,1 icpc'"
    print "Example: 'python benchmark.py 2 0,2 g++'"
    exit(0)

_EigenRoot = "/home/ps072922/projects/eigen-3.3.3/"
_affinity = sys.argv[2]
_compiler = sys.argv[3]

#######################
# Default settings
######################
_floatType = "float"
_beta = 1.0
_numThreads = int(sys.argv[1])
_minBlock = 16
_sizeMB = 200 # in MB
_leadingDimMultiple = 16 #the stride-1 index of both 'A' and 'B' have to be a multiple of this value (useful if a special alignment is required)


if _floatType == "float":
    _floatTypeSize = 4.
elif _floatType == "double":
    _floatTypeSize = 8
elif _floatType == "complex":
    _floatTypeSize = 8
elif _floatType == "doubleComplex":
    _floatTypeSize = 16

###################
# DO NOT MODIFY:
###################
_permutations = [
                    [[1,0]],
                    [[0,2,1],[1,0,2],[2,1,0]],
                    [[0,3,2,1],[2,1,3,0],[2,0,3,1],[1,0,3,2],[3,2,1,0]],
                    [[0,4,2,1,3],[3,2,1,4,0],[2,0,4,1,3],[1,3,0,4,2],[4,3,2,1,0]],
                    [[0,3,2,5,4,1],[3,2,0,5,1,4],[2,0,4,1,5,3],[3,2,5,1,0,4],[5,4,3,2,1,0]]
               ]



_genString = "ttc --beta=%f --maxImplementations=500 --numThreads=%d --compiler=%s --architecture=avx --affinity=%s"%(_beta,_numThreads,_compiler,_affinity)


def output(size, perm, fileHandle, fileHandleEigen, counter):
        sizeStr = ""
        for s in size:
            sizeStr += str(s)+","
        sizeStr = sizeStr[0:-1] #delete last ','
        permStr = ""
        for s in perm:
            permStr += str(s)+","
        permStr = permStr[0:-1] #delete last ','
        fileHandle.write(_genString +" --size="+sizeStr + " --perm="+permStr+"\n")
        print permStr, "&", sizeStr

        filename = "eigen%d.cpp"%counter
        fileHandle = open(filename,"w")
        code = eigen.genEigen(size, perm, _floatType, _floatTypeSize, _numThreads)
        fileHandle.write(code)
        fileHandle.close()
        fileHandleEigen.write("icpc -O3 -I%s -std=c++14 -qopenmp -xHost %s\n"%(_EigenRoot,filename)) #O0 is used to avoid that the compiler removes trashCache()
        fileHandleEigen.write("KMP_AFFINITY=compact,1 OMP_NUM_THREADS=%d numactl --interleave=all ./a.out >>eigen.dat\n"%_numThreads)
        counter += 1


fileHandle = open("benchmark.sh","w")
fileHandleEigen = open("benchmarkEigen.sh","w")
fileHandleEigen.write("rm -f eigen.dat\n")

counter = 0
for dim in range(2,7):

    numElements = _sizeMB/_floatTypeSize * 2.**20 #size in elements

    #determine the value for which base**dim yields roughly an array of size 'sizeMB'
    base = int(math.pow(numElements, 1./dim))

    for perm in _permutations[dim-2]:
        #make the first dimension a multiple of the minBlockSize
        size0 = (int(base + _minBlock - 1) / _minBlock) * _minBlock

        #the first 0-dim as well as the perm[0]-dimension will have size0 elements each
        numElementsTmp = numElements/(size0*size0)
        if(dim > 2):
            baseTmp = int(math.pow(numElementsTmp, 1./(dim-2)))
        else:
            baseTmp = 1

        size = [ baseTmp for i in range(dim)]

        if( perm[0] == 0):
            size[1] = size0
            size[perm[1]] = size0
        else:
            size[0] = size0
            size[perm[0]] = size0

        ################
        # at this point we have a size which is fairly similar in each dimension. 
        #
        # Now let's generate three different sizes for each permutation.
        ################

        sizeTmp = copy.deepcopy(size)
        if( sizeTmp[0] % _leadingDimMultiple != 0):
            sizeTmp[0] += (_leadingDimMultiple - sizeTmp[0]%_leadingDimMultiple)
        if( sizeTmp[perm[0]] % _leadingDimMultiple != 0):
            sizeTmp[perm[0]] += (_leadingDimMultiple - sizeTmp[perm[0]]%_leadingDimMultiple)

        ### 1) everything pretty equal
        output(sizeTmp, perm, fileHandle, fileHandleEigen, counter)
        counter+=1

        if dim >= 6:
            scewFactor = 3
        else:
            scewFactor = 6
        sizeTmp = copy.deepcopy(size)
        ### 2) skewed in 0-dim
        sizeTmp[0] *= scewFactor
        for i in range(1,dim):
            if( sizeTmp[i] > scewFactor and (perm[0] != i  or dim == 2)):
                sizeTmp[i] /= scewFactor
                break
        # ensure that the sizeTmp is close to the desired value
        totalElements = 1
        for s in sizeTmp:
            totalElements *= s
        sizeTmpMax = int(numElements / (totalElements / max(sizeTmp)))
        sizeTmp[sizeTmp.index(max(sizeTmp))] = sizeTmpMax

        if( sizeTmp[0] % _leadingDimMultiple != 0):
            sizeTmp[0] += (_leadingDimMultiple - sizeTmp[0]%_leadingDimMultiple)
        if( sizeTmp[perm[0]] % _leadingDimMultiple != 0):
            sizeTmp[perm[0]] += (_leadingDimMultiple - sizeTmp[perm[0]]%_leadingDimMultiple)

        output(sizeTmp, perm, fileHandle, fileHandleEigen, counter)
        counter+=1

        ### 3) skewed in perm[0]-dim
        sizeTmp = copy.deepcopy(size) #restore old size
        idx = 0
        if( perm[0] == 0 ):
            idx = 1

        sizeTmp[perm[idx]] *= scewFactor
        if( dim == 2 ):
            sizeTmp[0] /= scewFactor
        else:
            for i in range(1,dim):
                if( sizeTmp[i] > scewFactor and (perm[idx] != i)):
                    sizeTmp[i] /= scewFactor
                    break
        # ensure that the sizeTmp is close to the desired value
        totalElements = 1
        for s in sizeTmp:
            totalElements *= s
        sizeTmpMax = int(numElements / (totalElements / max(sizeTmp)))
        sizeTmp[sizeTmp.index(max(sizeTmp))] = sizeTmpMax

        if( sizeTmp[0] % _leadingDimMultiple != 0):
            sizeTmp[0] += (_leadingDimMultiple - sizeTmp[0]%_leadingDimMultiple)
        if( sizeTmp[perm[0]] % _leadingDimMultiple != 0):
            sizeTmp[perm[0]] += (_leadingDimMultiple - sizeTmp[perm[0]]%_leadingDimMultiple)

        output(sizeTmp, perm, fileHandle, fileHandleEigen, counter)
        counter+=1

fileHandle.close()
fileHandleEigen.close()





