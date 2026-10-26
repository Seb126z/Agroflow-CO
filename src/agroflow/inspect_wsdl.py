from zeep import Client
from .config import settings

client = Client(settings.sipsa_wsdl)

for service_name, service in client.wsdl.services.items():
    print(f"\nSERVICE: {service_name}")
    for port_name, port in service.ports.items():
        print(f"PORT: {port_name}")
        for name, operation in port.binding._operations.items():
            print(f"  {name}")
            print(f"    input: {operation.input.signature()}")
            print(f"    output: {operation.output.signature()}")
