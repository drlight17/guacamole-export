import xml.etree.ElementTree as ET
import json
import sys
import os

def convert_rdm_to_guac_json(xml_file_path):
    """
    Converts an RDM XML export file to a JSON array of basic Guacamole connection definitions.

    Args:
        xml_file_path (str): Path to the input RDM XML file.

    Returns:
        str: The resulting JSON string, or an error message.
    """
    if not os.path.exists(xml_file_path):
        return f"Error: File not found: {xml_file_path}"

    try:
        tree = ET.parse(xml_file_path)
        root = tree.getroot()
    except ET.ParseError as e:
        return f"Error parsing XML file: {e}"
    except Exception as e:
        return f"Error reading file: {e}"

    connections = []
    used_names = set() # Keep track of names already added to the JSON

    # Iterate through each Connection element
    for conn_element in root.findall('.//Connection'):
        conn_type_elem = conn_element.find('ConnectionType')
        if conn_type_elem is not None:
            conn_type = conn_type_elem.text

            # --- SSH Conversion ---
            if conn_type == 'SSHShell':
                terminal = conn_element.find('Terminal')
                if terminal is not None:
                    host_elem = terminal.find('Host')
                    port_elem = terminal.find('HostPort')
                    user_elem = terminal.find('Username')
                    pass_elem = terminal.find('SafePassword') # Note: Encrypted in RDM
                    command_elem = terminal.find('RemoteCommand')
                    name_elem = conn_element.find('Name')
                    # Extract the Group
                    group_elem = conn_element.find('Group')
                    rdm_group_path = group_elem.text if group_elem is not None else '' # Use empty string if no group

                    host = host_elem.text if host_elem is not None else ''
                    port = int(port_elem.text) if port_elem is not None and port_elem.text.isdigit() else 22 # Default SSH port
                    username = user_elem.text if user_elem is not None else ''
                    password = pass_elem.text if pass_elem is not None else '' # Note: Encrypted
                    command = command_elem.text if command_elem is not None else ''
                    name = name_elem.text if name_elem is not None else f"SSH_{host}:{port}" # Fallback name
                    protocol = "SSH"

                    # Create a Guacamole-like connection object (basic structure)
                    guac_connection = {
                        "name": name,
                        "protocol": "ssh", # Guacamole protocol
                        "parameters": {
                            "hostname": host,
                            "port": port,
                            "username": username,
                            # 'password' field in Guacamole JSON often expects plain text or is handled via credentials provider.
                            # Using the RDM 'SafePassword' directly will likely fail without decryption.
                            # "password": password, # Omitting due to encryption mismatch
                            "remote-app": command if command else "", # 'remote-app' sometimes used for commands, or 'command'
                            "command": command if command else ""      # 'command' is another option in Guacamole
                        }
                    }
                    # Add the RDM group as the 'group' attribute for Guacamole, converting path separators
                    if rdm_group_path:
                        # Replace backslashes with forward slashes and prepend 'ROOT/'
                        guac_group_path = 'ROOT/' + rdm_group_path.replace('\\', '/')
                        guac_connection["group"] = guac_group_path

            # --- RDP Conversion ---
            elif conn_type in ['RDP', 'RDPConfigured']: # Handle both standard and configured RDP types
                rdp_section = conn_element.find('RDP')
                if rdp_section is not None:
                    host_elem = rdp_section.find('Host') or conn_element.find('Url') # RDP might use 'Url' instead of 'Host' in RDM
                    port_elem = rdp_section.find('Port') # RDP port might be in RDP section
                    user_elem = rdp_section.find('UserName')
                    pass_elem = rdp_section.find('SafePassword') # Note: Encrypted in RDM
                    domain_elem = rdp_section.find('Domain')
                    name_elem = conn_element.find('Name')
                    # Extract the Group
                    group_elem = conn_element.find('Group')
                    rdm_group_path = group_elem.text if group_elem is not None else '' # Use empty string if no group
                    # Screen sizing mode
                    screen_mode_elem = rdp_section.find('ScreenSizingMode')
                    screen_mode = screen_mode_elem.text if screen_mode_elem is not None else ''

                    host = host_elem.text if host_elem is not None else ''
                    # Default RDP port if not specified
                    port = int(port_elem.text) if port_elem is not None and port_elem.text.isdigit() else 3389
                    username = user_elem.text if user_elem is not None else ''
                    password = pass_elem.text if pass_elem is not None else '' # Note: Encrypted
                    domain = domain_elem.text if domain_elem is not None else ''
                    name = name_elem.text if name_elem is not None else f"RDP_{host}:{port}" # Fallback name
                    protocol = "RDP"

                    guac_params = {
                        "hostname": host,
                        "port": port,
                        "username": username,
                        # "password": password, # Omitting due to encryption mismatch
                    }
                    if domain:
                        guac_params["domain"] = domain

                    # Map RDM screen sizing to Guacamole display mode
                    if screen_mode == 'FitToWindow':
                        guac_params["resize-method"] = "scale" # Guacamole's equivalent
                    elif screen_mode == 'FullScreen':
                         guac_params["resize-method"] = "none" # Or potentially use fullscreen parameters
                         # guac_params["enable-fullscreen"] = "true" # Alternative Guacamole param

                    # Create a Guacamole-like connection object (basic structure)
                    guac_connection = {
                        "name": name,
                        "protocol": "rdp", # Guacamole protocol
                        "parameters": guac_params
                    }
                    # Add the RDM group as the 'group' attribute for Guacamole, converting path separators
                    if rdm_group_path:
                        # Replace backslashes with forward slashes and prepend 'ROOT/'
                        guac_group_path = 'ROOT/' + rdm_group_path.replace('\\', '/')
                        guac_connection["group"] = guac_group_path

            # --- VNC Conversion (if applicable) ---
            elif conn_type == 'VNC':
                 vnc_section = conn_element.find('VNC')
                 if vnc_section is not None:
                     host_elem = vnc_section.find('Host')
                     port_elem = vnc_section.find('Port')
                     pass_elem = vnc_section.find('MsSafePassword') # VNC might use MsSafePassword or SafePassword
                     user_elem = vnc_section.find('MsUser') # VNC might use MsUser or Username
                     name_elem = conn_element.find('Name')
                     # Extract the Group
                     group_elem = conn_element.find('Group')
                     rdm_group_path = group_elem.text if group_elem is not None else '' # Use empty string if no group

                     host = host_elem.text if host_elem is not None else ''
                     port = int(port_elem.text) if port_elem is not None and port_elem.text.isdigit() else 5900
                     password = pass_elem.text if pass_elem is not None else '' # Note: Encrypted
                     username = user_elem.text if user_elem is not None else '' # VNC often doesn't use username, but RDM might store it
                     name = name_elem.text if name_elem is not None else f"VNC_{host}:{port}" # Fallback name
                     protocol = "VNC"

                     guac_params = {
                         "hostname": host,
                         "port": port,
                         # "password": password, # Omitting due to encryption mismatch
                     }
                     if username:
                         guac_params["username"] = username # Add username if present

                     guac_connection = {
                         "name": name,
                         "protocol": "vnc", # Guacamole protocol
                         "parameters": guac_params
                     }
                     # Add the RDM group as the 'group' attribute for Guacamole, converting path separators
                     if rdm_group_path:
                         # Replace backslashes with forward slashes and prepend 'ROOT/'
                         guac_group_path = 'ROOT/' + rdm_group_path.replace('\\', '/')
                         guac_connection["group"] = guac_group_path

            # --- Handle Connection Object (if created) ---
            else:
                 # If the connection type isn't handled, skip to the next element
                 continue

            # --- Name Uniqueness Check ---
            original_name = guac_connection["name"]
            unique_name = original_name
            counter = 1
            while unique_name in used_names:
                unique_name = f"{original_name} ({protocol})"
                if counter > 1:
                    unique_name += f"_{counter}"
                counter += 1

            guac_connection["name"] = unique_name
            used_names.add(unique_name) # Add the final unique name to the set
            connections.append(guac_connection) # Add the connection object to the list


    # Output the resulting JSON
    if connections:
        return json.dumps(connections, indent=4)
    else:
        return "No supported connections (SSHShell, RDP, RDPConfigured, VNC) found in the provided XML."

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python rdm_to_guac_json.py <path_to_rdm_xml_file>")
        sys.exit(1)

    input_xml_file = sys.argv[1]
    result_json = convert_rdm_to_guac_json(input_xml_file)

    print(result_json)