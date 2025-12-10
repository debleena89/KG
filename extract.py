from rdflib import Graph, Literal, RDF, RDFS, Namespace
import urllib.parse
import re

def extract_entities(module_name, input_ports, output_ports, signals, parameters, operations, ast=None):
    modules = [{
        'name': module_name,
        'input_ports': [{'name': name, 'direction': 'input', 'width': width} for name, width in input_ports],
        'output_ports': [{'name': name, 'direction': 'output', 'width': width} for name, width in output_ports],
        'signals': [{'name': name, 'type': s_type, 'width': width} for name, s_type, width in signals],
        'parameters': [{'name': name, 'value': value} for name, value in parameters],
        'operations': operations
    }]
    print("in the extract file")
    

    signal_dict = {}
    for port in modules[0]['input_ports'] + modules[0]['output_ports'] + modules[0]['signals']:
        signal_dict[port['name']] = {
            'width': port['width'],
            'type': port.get('type', 'wire' if port.get('direction') in ['input', 'output'] else port.get('type')),
            'module': module_name,
            'direction': port.get('direction', 'internal')
        }

    param_dict = {param['name']: {
        'value': param['value'],
        'module': module_name
    } for param in modules[0]['parameters']}

    operation_dict = {op['id']: {
        'type': op['type'],
        'target': op['target'],
        'expression': op['expression'],
        'operands': op['operands'],
        'context': op['context'],
        'module': module_name
    } for op in operations}
    
    relationships = []
    for op in operations:
        op_id = op['id']
        for operand in op['operands']:
            operand_clean = re.sub(r'\[\d+:\d+\]', '', operand)
            if operand_clean in signal_dict:
                relationships.append({
                    'source': f"operation_{urllib.parse.quote(op_id)}",
                    'target': f"signal_{urllib.parse.quote(operand_clean)}",
                    'type': 'uses_signal'
                })
        target_clean = re.sub(r'\[\d+:\d+\]', '', op['target'])
        if target_clean in signal_dict:
            relationships.append({
                'source': f"operation_{urllib.parse.quote(op_id)}",
                'target': f"signal_{urllib.parse.quote(target_clean)}",
                'type': 'produces_signal'
            })
        for param_name in param_dict:
            if param_name in op['expression']:
                relationships.append({
                    'source': f"operation_{urllib.parse.quote(op_id)}",
                    'target': f"param_{urllib.parse.quote(param_name)}",
                    'type': 'depends_on_parameter'
                })
        if op['type'] == 'INSTANTIATION':
            module_type = op['expression'].split('(')[0]
            relationships.append({
                'source': f"module_{urllib.parse.quote(module_name)}",
                'target': f"module_{urllib.parse.quote(module_type)}",
                'type': 'instantiates'
            })

    for signal_name, signal_info in signal_dict.items():
        for param_name in param_dict:
            if param_name in signal_info['width']:
                relationships.append({
                    'source': f"signal_{urllib.parse.quote(signal_name)}",
                    'target': f"param_{urllib.parse.quote(param_name)}",
                    'type': 'uses_parameter'
                })
    for m in modules:
        print("Module Name:", m["name"])
        print("Input Ports:", m["input_ports"])
        print("Output Ports:", m["output_ports"])
        print("Signals:", m["signals"])
        print("Parameters:", m["parameters"])
        print("Operations:", m["operations"])
    return modules, signal_dict, param_dict, operation_dict, relationships

def create_knowledge_graph(modules, signals, parameters, operations, relationships, output_file):
    g = Graph()
    EX = Namespace('http://example.org/hw#')
    g.bind('ex', EX)
    print("here in create graph fiel")
    g.add((EX.Module, RDF.type, RDFS.Class))
    g.add((EX.Signal, RDF.type, RDFS.Class))
    g.add((EX.Parameter, RDF.type, RDFS.Class))
    g.add((EX.Operation, RDF.type, RDFS.Class))
    g.add((EX.hasInput, RDF.type, RDF.Property))
    g.add((EX.hasOutput, RDF.type, RDF.Property))
    g.add((EX.hasInternalSignal, RDF.type, RDF.Property))
    g.add((EX.hasParameter, RDF.type, RDF.Property))
    g.add((EX.performsOperation, RDF.type, RDF.Property))
    g.add((EX.hasExpression, RDF.type, RDF.Property))
    g.add((EX.usesSignal, RDF.type, RDF.Property))
    g.add((EX.producesSignal, RDF.type, RDF.Property))
    g.add((EX.dependsOnParameter, RDF.type, RDF.Property))
    g.add((EX.usesParameter, RDF.type, RDF.Property))
    g.add((EX.instantiates, RDF.type, RDF.Property))

    for module in modules:
        module_uri = EX[f"module_{urllib.parse.quote(module['name'])}"]
        g.add((module_uri, RDF.type, EX.Module))
        g.add((module_uri, RDFS.label, Literal(module['name'])))

        for port in module['input_ports']:
            signal_uri = EX[f"signal_{urllib.parse.quote(port['name'])}"]
            g.add((signal_uri, RDF.type, EX.Signal))
            g.add((signal_uri, RDFS.label, Literal(port['name'])))
            g.add((signal_uri, EX.width, Literal(port['width'])))
            g.add((signal_uri, EX.direction, Literal('input')))
            g.add((module_uri, EX.hasInput, signal_uri))

        for port in module['output_ports']:
            signal_uri = EX[f"signal_{urllib.parse.quote(port['name'])}"]
            g.add((signal_uri, RDF.type, EX.Signal))
            g.add((signal_uri, RDFS.label, Literal(port['name'])))
            g.add((signal_uri, EX.width, Literal(port['width'])))
            g.add((signal_uri, EX.direction, Literal('output')))
            g.add((module_uri, EX.hasOutput, signal_uri))

        for signal_name, signal_info in signals.items():
            if signal_info['module'] == module['name'] and signal_info['direction'] == 'internal':
                signal_uri = EX[f"signal_{urllib.parse.quote(signal_name)}"]
                g.add((signal_uri, RDF.type, EX.Signal))
                g.add((signal_uri, RDFS.label, Literal(signal_name)))
                g.add((signal_uri, EX.width, Literal(signal_info['width'])))
                g.add((signal_uri, EX.signalType, Literal(signal_info['type'])))
                g.add((signal_uri, EX.direction, Literal('internal')))
                g.add((module_uri, EX.hasInternalSignal, signal_uri))

        for param_name, param_info in parameters.items():
            if param_info['module'] == module['name']:
                param_uri = EX[f"param_{urllib.parse.quote(param_name)}"]
                g.add((param_uri, RDF.type, EX.Parameter))
                g.add((param_uri, RDFS.label, Literal(param_name)))
                g.add((param_uri, EX.value, Literal(param_info['value'])))
                g.add((module_uri, EX.hasParameter, param_uri))

        for op_id, op_info in operations.items():
            if op_info['module'] == module['name']:
                op_uri = EX[f"operation_{urllib.parse.quote(op_id)}"]
                g.add((op_uri, RDF.type, EX.Operation))
                g.add((op_uri, RDFS.label, Literal(op_info['type'])))
                g.add((op_uri, EX.target, Literal(op_info['target'])))
                g.add((op_uri, EX.hasExpression, Literal(op_info['expression'])))
                g.add((op_uri, EX.context, Literal(op_info['context'])))
                for operand in op_info['operands']:
                    operand_clean = re.sub(r'\[\d+:\d+\]', '', operand)
                    if operand_clean in signals:
                        signal_uri = EX[f"signal_{urllib.parse.quote(operand_clean)}"]
                        g.add((op_uri, EX.usesSignal, signal_uri))
                g.add((module_uri, EX.performsOperation, op_uri))

    for rel in relationships:
        source_uri = EX[rel['source']]
        target_uri = EX[rel['target']]
        rel_type = EX[rel['type'].replace('_', '')]
        g.add((source_uri, rel_type, target_uri))

    g.serialize(destination=output_file, format='turtle')
    print(f'Knowledge graph saved to {output_file}')