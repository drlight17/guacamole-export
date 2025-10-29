import psycopg2
import json
import sys
import os
from urllib.parse import urlparse

# --- Configuration ---
# Replace these with your PostgreSQL connection details for the Guacamole database
# You might find these in your Guacamole server's guacamole.properties file
DB_HOST = "localhost"      # e.g., "localhost", "db.internal", or an IP
DB_PORT = "5432"              # Default PostgreSQL port, change if needed
DB_NAME = "guacamole_db"      # The database name Guacamole uses
DB_USER = "guacamole_user"    # The database user Guacamole uses
DB_PASS = "guacamole_user_password"    # The password for that user

# Output file path
OUTPUT_FILE = "guacamole_connections_db_export.json"
# --- End Configuration ---

def connect_to_db(host, port, database, user, password):
    """
    Connects to the PostgreSQL database.
    """
    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password
        )
        return conn
    except psycopg2.Error as e:
        print(f"Error connecting to PostgreSQL database: {e}")
        sys.exit(1)

def fetch_connections_and_params(conn):
    """
    Fetches connections and their parameters from the database.
    Joins guacamole_connection, guacamole_connection_group (for parent group),
    and guacamole_connection_parameter.
    """
    cursor = conn.cursor()

    # Query to get connection details, its parent group name (if not ROOT),
    # and all its parameters (including encrypted password).
    # This query focuses on getting the core data.
    query = """
    WITH RECURSIVE connection_group_path AS (
      SELECT
        connection_group_id,
        connection_group_name,
        parent_id,
        CAST(connection_group_name AS character varying) AS full_path
      FROM guacamole_connection_group
      WHERE parent_id IS NULL

      UNION ALL

      SELECT
        cg.connection_group_id,
        cg.connection_group_name,
        cg.parent_id,
        cgp.full_path || '/' || cg.connection_group_name AS full_path
      FROM guacamole_connection_group cg
      JOIN connection_group_path cgp ON cg.parent_id = cgp.connection_group_id
    )
    SELECT
        c.connection_id,
        c.connection_name,
        'ROOT/' || COALESCE(cgp.full_path, '') AS group_path,
        c.protocol,
        p.parameter_name,
        p.parameter_value
    FROM guacamole_connection c
    LEFT JOIN connection_group_path cgp ON c.parent_id = cgp.connection_group_id
    LEFT JOIN guacamole_connection_parameter p ON c.connection_id = p.connection_id
    ORDER BY
        c.connection_name,
        p.parameter_name;
    """

    try:
        cursor.execute(query)
        rows = cursor.fetchall()
        return rows
    except psycopg2.Error as e:
        print(f"Error executing database query: {e}")
        sys.exit(1)
    finally:
        cursor.close()

def build_connection_dict(rows):
    """
    Builds a dictionary of connections from the query results.
    Each connection ID maps to its details (name, group, parameters).
    """
    connections_map = {}

    for row in rows:
        conn_id, name, parent_id, group_name, param_name, param_value = row

        if conn_id not in connections_map:
            connections_map[conn_id] = {
                "name": name,
                "protocol": group_name,
                "group": parent_id, # Include the parent group ID if needed for structure
                "parameters": {}
            }

        # Add the parameter to the connection's parameter dictionary
        if param_name is not None: # Handle cases where parameter_name might be NULL
            connections_map[conn_id]["parameters"][param_name] = param_value

    # Convert the map values (which are the connection objects) into a list
    return list(connections_map.values())


def main():
    print("Starting Guacamole PostgreSQL Export Script...")
    print(f"Target Database: {DB_NAME} on {DB_HOST}:{DB_PORT}")
    print(f"Target Output File: {OUTPUT_FILE}")

    # Validate configuration
    if not all([DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASS]):
        print("Error: Please configure all DB_* variables in the script.")
        sys.exit(1)

    print("\nConnecting to PostgreSQL database...")
    conn = connect_to_db(DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASS)
    print("Connected successfully.")

    print("\nFetching connections and parameters from database...")
    raw_data = fetch_connections_and_params(conn)
    print(f"Fetched {len(raw_data)} parameter rows.")

    print("\nBuilding connection objects...")
    connections_list = build_connection_dict(raw_data)
    print(f"Built {len(connections_list)} connection objects.")

    # Prepare the final output structure
    #export_data = {
    #    "exported_from_database": f"{DB_HOST}:{DB_PORT}/{DB_NAME}",
    #    "export_timestamp": json.dumps({"$type": "date", "value": int(__import__('time').time())}), # Use local system time for export timestamp
    #    "total_connections_found": len(connections_list),
    #    "connections": connections_list
    #}
    export_data = connections_list

    print(f"\nWriting export to {OUTPUT_FILE}...")
    try:
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=4, ensure_ascii=False)
        print(f"Export completed successfully. Data written to '{OUTPUT_FILE}'.")
        print("*** WARNING: This file contains sensitive data including ENCRYPTED passwords stored in the database. Store it securely and delete it after use. ***")
    except IOError as e:
        print(f"Error writing to file {OUTPUT_FILE}: {e}")
        sys.exit(1)
    finally:
        # Ensure the database connection is closed
        if conn:
            conn.close()
            print("Database connection closed.")


if __name__ == "__main__":
    main()
