import copy
import subprocess

OKGREEN = '\033[92m'
FAIL = '\033[91m'
WARNING = '\033[93m'
ENDC = '\033[0m'

class TTCargs:
    def __init__ (self,idxPerm, size):
        self.size = copy.deepcopy(size)
        self.idxPerm= copy.deepcopy(idxPerm)
        self.alpha = 1.
        self.beta = 0.
        self.affinity = ""
        self.numThreads = 0
        self.floatTypeA = "float"
        self.floatTypeB = "float"
        self.streamingStores = 0
        self.maxNumImplementations = 200
        self.lda = []
        self.ldb = []
        self.debug = 0
        self.architecture= "avx"
        self.align = 1
        self.blockings = []
        self.loopPermutations = []
        self.prefetchDistances = []
        self.scalar = 0
        self.silent = 0
        self.ignoreDatabase = 0
        self.compiler = "intel"
        self.hostName = ""
        self.vecLength = []
        self.hotA = 0
        self.hotB = 0
        self.updateDatabase = 1

    def getSize(self):
        return copy.deepcopy(self.size)

    def getPerm(self):
        return copy.deepcopy(self.idxPerm)


def getCudaErrorChecking(indent, routine):
   tmpCode =indent+"{cudaError_t err = cudaGetLastError();\n"
   tmpCode +=indent+"if(err != cudaSuccess){\n"
   tmpCode +=indent+"   printf(\"\\nKernel ERROR in %s: %%s (line: %%d)\\n\", cudaGetErrorString(err), __LINE__);\n"%routine
   tmpCode +=indent+"   exit(-1);\n"
   tmpCode +=indent+"}}\n"
   return tmpCode


    
def listToString(l):
    out = ""
    if(len(l) > 0):
        out = "("
        for idx in l:
            out += str(idx) + ","
        out = out[:-1] + ")"
    return out

def getArchitecture(arch):
    if( arch == "cuda" ):
        try:
            proc = subprocess.Popen(["nvidia-smi", "-L"],stdout=subprocess.PIPE)
            proc.wait()
        except OSError:
            print FAIL + "[TTC] ERROR: nvidia-smi not found"%comp +ENDC
            exit(-1)

        return proc.communicate()[0].split(":")[1]
    else:
        f = open("/proc/cpuinfo", "r")
        for l in f:
            if( l.find("model name") != -1):
                arch = l.split(":")[1]
                pos = arch.find("@")
                f.close()
                return arch[0:pos]

def getCostLoop(loopPerm, perm, size):

    #compute leading dimensions
    lda = [1]
    ldb = [1]
    for i in range(1,len(size)):
        lda.append(lda[i-1]*size[i-1])
        ldb.append(ldb[i-1]*size[perm[i-1]])


    totalSize = 1
    cost = 0
    for i in range(len(loopPerm)):
        loopIdx  = loopPerm[i]

        #find the position of index 'loopIdx' in the output B
        idxB = -1
        for j in range(len(perm)):
            if perm[j] == loopIdx:
                idxB = j
                break
        
        lda0 = lda[loopIdx]
        ldb0 = ldb[idxB]

        lastOffsetA = 0 #offset in A, if all following loops are in their last iteration
        lastOffsetB = 0 #offset in B, if all following loops are in their last iteration
        for l in range(i+1, len(loopPerm)):
            loopIdxNext = loopPerm[l]

            #find the position of index 'loopIdx' in the output B
            idxBNext = -1
            for j in range(len(perm)):
                if perm[j] == loopIdxNext:
                    idxBNext = j
                    break
            lastOffsetA += lda[loopIdxNext] * (size[loopIdxNext]-1)
            lastOffsetB += ldb[idxBNext] * (size[loopIdxNext]-1)

        cost += totalSize*(size[loopIdx]-1) * ((lastOffsetA - lda0)**2. + (lastOffsetB - ldb0)**2.)
        totalSize *= size[loopIdx]

    return cost


#fuse consecutive indices in perm and invPerm to a single index (i.e., perform loop fusion)
#size array of sizes corresponding to perm
def fuseIndices(size, perm, loopPermutations, lda, ldb):
    inputIndices = range(len(size))
    #find all contiguous indices in inputIndices and invinputIndices
    for i in range(len(inputIndices)):
        for j in range(len(perm)):
            l = 0
            newSize = 1
            while i+l < len(inputIndices) and j+l < len(perm) and inputIndices[i+l] == perm[j+l] and (l == 0 or lda[i+l] == lda[i+l-1] * size[i+l-1]) and (l == 0 or ldb[j+l] == ldb[j+l-1] * size[i+l-1]): #make sure that those indices will be cont. in A
                newSize *= size[i+l]
                l += 1

            if l >= 1:
                size[i] = newSize

            while l > 1:
                inputIndices.pop(i+1)
                perm.pop(j+1)
                size.pop(i+1)
                lda.pop(i+1)
                ldb.pop(j+1)
                l -= 1

    #remove gabs in permutation (e.g.: [0,1,3]->[0,1,2])
    for i in range(len(inputIndices)):
        #find smallest entry with >=i
        smallestEntry = 100000
        smallestEntryIdx = -1 
        for j in range(len(inputIndices)):
            if inputIndices[j] >= i and inputIndices[j] <= smallestEntry:
                smallestEntry = inputIndices[j]
                smallestEntryIdx = j
        inputIndices[smallestEntryIdx] = i
    for i in range(len(perm)):
        #find smallest entry with >=i
        smallestEntry = 100000
        smallestEntryIdx = -1 
        for j in range(len(perm)):
            if perm[j] >= i and perm[j] <= smallestEntry:
                smallestEntry = perm[j]
                smallestEntryIdx = j
        perm[smallestEntryIdx] = i

    for loopOrder in loopPermutations:
        k=0
        removeList = []
        diff=len(loopOrder)-len(perm)
        for i in range(len(loopOrder)):
            loopOrder[i] = loopOrder[i] - diff 
            if(loopOrder[i] < 0):
                removeList.append(loopOrder[i])
                k +=1
        for i in range(len(removeList)):
            loopOrder.remove(removeList[i])

def getCompilerVersion(compiler):
    comp = ""
    if( compiler == "intel" ):
        comp = "icpc"
    if( compiler == "gcc" ):
        comp = "g++"
    if( compiler == "ibm" ):
        comp = "bgxlc"
    if( compiler == "nvcc"):
	comp = "nvcc"
    try:
        version = "--version"
        if( compiler == "ibm" ):
            version = "-qversion"
        proc = subprocess.Popen([comp, version],stdout=subprocess.PIPE)
        proc.wait()
    except OSError:
        print FAIL + "[TTC] ERROR: compiler '%s' not known. Please select a different compiler via --compiler=... "%comp +ENDC
        exit(-1)

    output = proc.communicate()[0].split("\n")
    return output[0]

