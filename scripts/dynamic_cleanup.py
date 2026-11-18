"""Delete only resources explicitly labelled as dynamic players of one project."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from frost.docker_api import Docker,DockerError


def cleanup(project):
    docker=Docker()
    for row in docker.containers(['frost.managed='+project]):
        docker.call('DELETE','/containers/'+row['Id']+'?force=1')
    for net in docker.call('GET','/networks'):
        if net.get('Labels',{}).get('frost.managed')!=project: continue
        info=docker.call('GET','/networks/'+net['Id'])
        for ident in info.get('Containers',{}):
            container=docker.call('GET','/containers/'+ident+'/json')
            labels=container['Config'].get('Labels',{}) or {}
            if labels.get('com.docker.compose.project')==project or labels.get('frost.managed')==project:
                docker.call('POST','/networks/'+net['Id']+'/disconnect',{'Container':ident,'Force':True})
        docker.call('DELETE','/networks/'+net['Id'])
    for volume in docker.call('GET','/volumes').get('Volumes',[]) or []:
        if (volume.get('Labels') or {}).get('frost.managed')==project:
            docker.call('DELETE','/volumes/'+volume['Name'])
