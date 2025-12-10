import re
from contextlib import redirect_stderr
import os
import io
import uuid
import pyverilog.vparser.parser as vparser
from pyverilog.vparser.parser import parse, Description, ModuleDef, Ioport, Port
def preprocess_verilog(code):
    def replace_idx(match):
        idx = match.group(1)
        return f'IDX{idx}'
    code = re.sub(r'`IDX\((\d+)\)', replace_idx, code)
    return code

def classify_operation(expr):
    expr = expr.strip()
    if '&' in expr and not '&&' in expr:
        op_type = 'AND'
        operands = re.findall(r'\b[\w\[\]:]+\b', expr.replace('&', ' '))
    elif '|' in expr and not '||' in expr:
        op_type = 'OR'
        operands = re.findall(r'\b[\w\[\]:]+\b', expr.replace('|', ' '))
    elif '^' in expr:
        op_type = 'XOR'
        operands = re.findall(r'\b[\w\[\]:]+\b', expr.replace('^', ' '))
    elif '+' in expr:
        op_type = 'ADD'
        operands = re.findall(r'\b[\w\[\]:]+\b', expr.replace('+', ' '))
    elif '-' in expr and not '->' in expr:
        op_type = 'SUBTRACT'
        operands = re.findall(r'\b[\w\[\]:]+\b', expr.replace('-', ' '))
    elif '<<' in expr:
        op_type = 'LSHIFT'
        operands = re.findall(r'\b[\w\[\]:]+\b', expr.replace('<<', ' '))
    elif '>>' in expr:
        op_type = 'RSHIFT'
        operands = re.findall(r'\b[\w\[\]:]+\b', expr.replace('>>', ' '))
    elif '~' in expr:
        op_type = 'NOT'
        operands = re.findall(r'\b[\w\[\]:]+\b', expr.replace('~', ' '))
    elif '<=' in expr:
        op_type = 'NON_BLOCKING_ASSIGN'
        operands = re.findall(r'\b[\w\[\]:]+\b', expr)
    elif '=' in expr and '==' not in expr:
        op_type = 'ASSIGN'
        operands = re.findall(r'\b[\w\[\]:]+\b', expr)
    else:
        op_type = 'UNKNOWN'
        operands = re.findall(r'\b[\w\[\]:]+\b', expr)
    return op_type, operands

def parse_verilog_code(code, temp_file='temp.v'):
    module_name = None
    input_ports = []
    output_ports = []
    signals = []
    parameters = []
    operations = []
    ast = None
    header_ports = []
    port_directions = {}

    code = preprocess_verilog(code)
    print("fiunction called")
    with open(temp_file, 'w') as f:
        f.write(code)

    try:
        f = io.StringIO()
        with redirect_stderr(f):
            ast, _ = parse([temp_file], preprocess_include=['./verilog/'], debug=False)
        if isinstance(ast.description, Description):
            for node in ast.description.definitions:
                if isinstance(node, ModuleDef):
                    module_name = node.name
                    if node.portlist:
                        for port in node.portlist.ports:
                            if isinstance(port, Ioport) and hasattr(port.first, 'name'):
                                port_name = port.first.name
                                width = '1'
                                if hasattr(port.first, 'width') and port.first.width:
                                    width = f'[{port.first.width.msb}:{port.first.width.lsb}]'
                                if isinstance(port.first, vparser.Input):
                                    input_ports.append((port_name, width))
                                elif isinstance(port.first, vparser.Output):
                                    output_ports.append((port_name, width))
                            elif isinstance(port, Port) and hasattr(port, 'name'):
                                header_ports.append((port.name, '1'))
    except Exception as e:
        print(f'Pyverilog parsing failed: {str(e)}')

    try:
        lines = code.splitlines()
        module_found = False
        in_module_decl = False
        port_section = []
        i = 0
        always_context = None

        while i < len(lines):
            line = lines[i].strip()
            if line.startswith('//') or not line:
                i += 1
                continue
            if line.startswith('module'):
                candidate_name = line.split()[1].split('(')[0].strip()
                module_name = candidate_name
                module_found = True
                if '(' in line:
                    in_module_decl = True
                    start_idx = line.index('(') + 1
                    if ')' in line:
                        port_section.append(line[start_idx:line.index(')')])
                        in_module_decl = False
                    else:
                        port_section.append(line[start_idx:])
                i += 1
                continue
            if in_module_decl:
                if ')' in line:
                    port_section.append(line[:line.index(')')])
                    in_module_decl = False
                else:
                    port_section.append(line)
                i += 1
                continue
            if module_found:
                port_match = re.match(r'^(input|output|inout)\s*(wire|reg)?\s*(\[[\w\-`]+:[0-9]+\])?\s*([\w,\s]+)\s*[,;]', line)
                if port_match:
                    direction = port_match.group(1)
                    width = port_match.group(3) if port_match.group(3) else '1'
                    port_names = [p.strip() for p in port_match.group(4).split(',') if p.strip()]
                    for port_name in port_names:
                        port_directions[port_name] = direction
                        if direction == 'input' and port_name not in [p[0] for p in input_ports]:
                            input_ports.append((port_name, width))
                        elif direction == 'output' and port_name not in [p[0] for p in output_ports]:
                            output_ports.append((port_name, width))
                signal_match = re.match(r'^(wire|reg)\s*(\[[\w\-`]+:[0-9]+\])?\s*([\w,\s]+)\s*;', line)
                if signal_match:
                    signal_type = signal_match.group(1)
                    width = signal_match.group(2) if signal_match.group(2) else '1'
                    signal_names = [s.strip() for s in signal_match.group(3).split(',')]
                    for signal_name in signal_names:
                        if signal_name not in [p[0] for p in input_ports + output_ports]:
                            signals.append((signal_name, signal_type, width))
                param_match = re.match(r'^parameter\s+(.+?);', line)
                if param_match:
                    param_str = param_match.group(1).strip()
                    param_pairs = re.split(r',\s*(?=\w+\s*=)', param_str)
                    for pair in param_pairs:
                        pair_match = re.match(r'(\w+)\s*=\s*([^,\s]+(?:\s*[^,\s]+)*)', pair.strip())
                        if pair_match:
                            param_name = pair_match.group(1).strip()
                            param_value = pair_match.group(2).strip()
                            print(f'Parsed parameter: name={param_name}, value={param_value}')
                            parameters.append((param_name, param_value))
                inst_match = re.match(r'^(\w+)\s+(\w+)\s*\(([^)]+)\);', line)
                if inst_match:
                    module_type = inst_match.group(1)
                    instance_name = inst_match.group(2)
                    ports = [p.strip() for p in inst_match.group(3).split(',')]
                    operations.append({
                        'id': str(uuid.uuid4()),
                        'type': 'INSTANTIATION',
                        'target': instance_name,
                        'expression': f"{module_type}({', '.join(ports)})",
                        'operands': ports,
                        'context': 'structural'
                    })
                assign_match = re.match(r'^assign\s+([\w\[\]:]+)\s*=\s*([^;]+);', line)
                if assign_match:
                    target = assign_match.group(1)
                    expr = assign_match.group(2).strip()
                    op_type, operands = classify_operation(expr)
                    operations.append({
                        'id': str(uuid.uuid4()),
                        'type': op_type,
                        'target': target,
                        'expression': expr,
                        'operands': operands,
                        'context': 'combinational'
                    })
                if line.startswith('always @'):
                    if '@(*)' in line or '@(' in line and 'posedge' not in line:
                        always_context = 'combinational'
                    elif 'posedge' in line:
                        always_context = 'sequential'
                    i += 1
                    while i < len(lines) and not lines[i].strip().startswith('endmodule'):
                        stmt = lines[i].strip()
                        if stmt and not stmt.startswith('//'):
                            nb_assign_match = re.match(r'^([\w\[\]:]+)\s*<\=\s*([^;]+);', stmt)
                            if nb_assign_match:
                                target = nb_assign_match.group(1).strip()
                                expr = nb_assign_match.group(2).strip()
                                op_type, operands = classify_operation(expr)
                                operations.append({
                                    'id': str(uuid.uuid4()),
                                    'type': op_type,
                                    'target': target,
                                    'expression': expr,
                                    'operands': operands,
                                    'context': always_context
                                })
                            block_assign_match = re.match(r'^([\w\[\]:]+)\s*=\s*([^;]+);', stmt)
                            if block_assign_match:
                                target = block_assign_match.group(1).strip()
                                expr = block_assign_match.group(2).strip()
                                op_type, operands = classify_operation(expr)
                                operations.append({
                                    'id': str(uuid.uuid4()),
                                    'type': op_type,
                                    'target': target,
                                    'expression': expr,
                                    'operands': operands,
                                    'context': always_context
                                })
                        i += 1
                    continue
            i += 1

        if port_section:
            port_text = ' '.join(port_section).replace(';', ',')
            port_list = [p.strip() for p in port_text.split(',') if p.strip() and not p.strip().startswith('//')]
            for port in port_list:
                match = re.match(r'^(input|output|inout)?\s*(wire|reg)?\s*(\[[\w\-`]+:[0-9]+\])?\s*(\w+)', port)
                if match and match.group(1):
                    width = match.group(3) if match.group(3) else '1'
                    port_name = match.group(4)
                    direction = match.group(1)
                    port_directions[port_name] = direction
                    if direction == 'input' and port_name not in [p[0] for p in input_ports]:
                        input_ports.append((port_name, width))
                    elif direction == 'output' and port_name not in [p[0] for p in output_ports]:
                        output_ports.append((port_name, width))
                else:
                    header_ports.append((port, '1'))

        for port_name, width in header_ports:
            direction = port_directions.get(port_name, 'input')
            if direction == 'input' and port_name not in [p[0] for p in input_ports]:
                input_ports.append((port_name, width))
            elif direction == 'output' and port_name not in [p[0] for p in output_ports]:
                output_ports.append((port_name, width))

        if not module_found:
            print('No valid module found in code')
        else:
            print(f'Parsed module: {module_name}')

    except Exception as e:
        print(f'Heuristic parsing failed: {str(e)}')

    if os.path.exists(temp_file):
        os.remove(temp_file)

    return module_name, input_ports, output_ports, signals, parameters, operations, ast