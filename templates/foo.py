import threading, time

BIGLIST = []

class Instance( object ):
    def __init__(self):
        print "init"
    def terminate( self):
        t_thread = threading.Thread(target = self.__terminate())
        t_thread.start()
        
    def __terminate( self ):
        BIGLIST.remove(self)
        #return True

if __name__ == "__main__":
    for i in range(3):
        iq = Instance()
        BIGLIST.append(iq)
        
    print BIGLIST
    
    iq.terminate()
    
    print "Sleeping for 3 seconds"
    time.sleep(3)
    
    print BIGLIST