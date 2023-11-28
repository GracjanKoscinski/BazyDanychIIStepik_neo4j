from flask import Flask, jsonify, request
from neo4j import GraphDatabase
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)

uri = os.getenv('URI')
user = os.getenv("USERNAME")
password = os.getenv("PASSWORD")
driver = GraphDatabase.driver(uri, auth=(user, password), database="neo4j")

# Wyszukiwanie pracowników
def get_employees(tx):
    result = tx.run("MATCH (e:Employee)-[:WORKS_IN]->(d:Department) RETURN e.name AS employee, e.position AS position, e.salary AS salary, d.name AS department")
    return [{"employee": record["employee"], "position": record["position"], "salary": record["salary"], "department": record["department"]} for record in result]

# Wyszukiwanie pracowników z opcjonalnym filtrowaniem i sortowaniem
def get_filtered_employees(tx, filter_criteria=None, sort_by=None):
    # Podstawowe zapytanie Cypher, które obejmuje pracowników i ich relacje MANAGES
    query = (
        "MATCH (e:Employee)-[:WORKS_IN]->(d:Department) "
        "OPTIONAL MATCH (e)-[:MANAGES]->(m:Employee) "
        "RETURN e.name AS employee, e.position AS position, e.salary AS salary, d.name AS department"
    )

    # Dodaj warunki filtrowania
    if filter_criteria:
        query += f" WHERE {filter_criteria}"

    # Dodaj kryterium sortowania
    if sort_by:
        query += f" ORDER BY {sort_by}"

    result = tx.run(query)
    return [{"employee": record["employee"], "position": record["position"], "salary": record["salary"],
             "department": record["department"]} for record in result]

@app.route('/employees', methods=['GET'])
def get_filtered_employees_route():
    filter_criteria = request.args.get('filter')
    sort_by = request.args.get('sort')

    with driver.session() as session:
        employees = session.read_transaction(get_filtered_employees, filter_criteria, sort_by)
        return jsonify(employees)

#dodawanie
def create_employee(tx, name, position, department, salary):
    # Sprawdź, czy istnieje już taki dział
    result = tx.run("MATCH (d:Department {name: $department}) RETURN count(d) AS count", department=department)
    department_exists = result.single()["count"] > 0

    # Jeżeli istnieje, dodaj pracownika do istniejącego działu, w przeciwnym razie utwórz nowy dział
    if department_exists:
        tx.run("MATCH (d:Department {name: $department}) "
               "CREATE (e:Employee {name: $name, position: $position, salary: $salary})-[:WORKS_IN]->(d)", name=name, position=position, department=department, salary=salary)
    else:
        tx.run("CREATE (e:Employee {name: $name, position: $position, salary: $salary})-[:WORKS_IN]->(d:Department {name: $department})", name=name, position=position, department=department, salary=salary)

 
def is_unique_employee(tx, name):
    result = tx.run("MATCH (e:Employee) WHERE e.name = $name RETURN count(e) AS count", name=name)
    return result.single()["count"] == 0

# dodawanie managerów   
def create_manager_relationship(tx, manager_name, employee_name):
    # Sprawdź, czy menadżer i pracownik istnieją
    result = tx.run("MATCH (m:Employee {name: $manager_name}) "
                    "MATCH (e:Employee {name: $employee_name}) "
                    "RETURN count(m) AS manager_count, count(e) AS employee_count",
                    manager_name=manager_name, employee_name=employee_name)
    counts = result.single()

    if counts["manager_count"] == 0 or counts["employee_count"] == 0:
        return {"error": "Menadżer lub pracownik nie istnieje"}, 404

    # Dodaj relację MANAGES między menadżerem a pracownikiem
    tx.run("MATCH (m:Employee {name: $manager_name}) "
           "MATCH (e:Employee {name: $employee_name}) "
           "CREATE (m)-[:MANAGES]->(e)", manager_name=manager_name, employee_name=employee_name)

@app.route('/employees', methods=['POST'])
def add_employee():
    data = request.get_json()

    # Sprawdź, czy wszystkie wymagane dane są dostępne
    required_fields = ['name', 'position', 'department', 'salary', 'relation']
    if not all(field in data for field in required_fields):
        return jsonify({"error": "Wszystkie wymagane dane (name, position, department, salary, relation) muszą być podane"}), 400

    name = data['name']
    position = data['position']
    department = data['department']
    salary = data['salary']
    relation = data['relation']

    # Sprawdź, czy imię i nazwisko są unikalne
    with driver.session() as session:
        if not session.execute_read(is_unique_employee, name):
            return jsonify({"error": "Pracownik o podanym imieniu i nazwisku już istnieje"}), 400

        # Dodaj pracownika do bazy danych
        if relation == "WORKS_IN":
            session.execute_write(create_employee, name, position, department, salary)
        elif relation == "MANAGES":
            employees = data.get("employees", [])
            if not employees:
                return jsonify({"error": "Aby dodać relację MANAGES, należy podać listę pracowników, którzy będą zarządzani"}), 400
        # Dodaj menadżera do bazy danych
            session.execute_write(create_employee, name, position, department, salary)
        # Dodaj relacje MANAGES między menadżerem a innymi pracownikami
            for employee_name in employees:
                session.execute_write(create_manager_relationship, name, employee_name)
        else:
            return jsonify({"error": "Nieprawidłowa wartość dla 'relation'"}), 400

    return jsonify({"message": "Pracownik dodany pomyślnie"}), 201

# Edytuj pracownika o określonym identyfikatorze (name, ponieważ jest unikalne)
def edit_employee(tx, name, data):
    query = f"MATCH (e:Employee) WHERE REPLACE(e.name, ' ', '') = $name SET"
    for key, value in data.items():
        query += f" e.{key} = ${key},"
    query = query.rstrip(',')  # Usuń ostatni przecinek
    query += " RETURN e"

    result = tx.run(query, name=name, **data)
    updated_employee = result.single()["e"]

    updated_employee_dict = dict(updated_employee)
    return updated_employee_dict

@app.route('/employees/<path:name>', methods=['PUT'])
def update_employee(name):
    name_without_spaces = name.replace(' ', '')

    data = request.get_json()

    with driver.session() as session:
        # Sprawdź, czy pracownik o podanym imieniu i nazwisku istnieje
        result = session.run("MATCH (e:Employee) WHERE REPLACE(e.name, ' ', '') = $name RETURN count(e) AS count", name=name_without_spaces)
        if result.single()["count"] == 0:
            return jsonify({"error": f"Pracownik o imieniu {name} nie istnieje"}), 404

        # Aktualizuj pracownika
        updated_employee = session.write_transaction(edit_employee, name_without_spaces, data)

    return jsonify({"message": f"Pracownik {name} zaktualizowany pomyślnie", "employee": updated_employee})


# Usuń pracownika o określonym imieniu i nazwisku
def delete_employee_by_name(tx, name):
    # Sprawdź, czy pracownik o podanym imieniu i nazwisku istnieje
    result = tx.run("MATCH (e:Employee) WHERE REPLACE(e.name, ' ', '') = $name RETURN count(e) AS count, e.position AS position", name=name)
    record = result.single()
    if record["count"] == 0:
        return False 

    position = record["position"]
    
    # Pobierz nazwę departamentu, jeżeli pracownik jest menadżerem
    if position == "manager":
        department_result = tx.run("MATCH (e:Employee)-[:WORKS_IN]->(d:Department) WHERE REPLACE(e.name, ' ', '') = $name RETURN d.name AS department_name", name=name)
        department_name = department_result.single()["department_name"]

    # Usuń pracownika
    tx.run("MATCH (e:Employee)-[r]->() WHERE REPLACE(e.name, ' ', '') = $name DELETE e, r", name=name)

    # Jeśli pracownik jest menadżerem, usuń także departament
    if position == "manager" and department_name:
        tx.run("MATCH (d:Department) WHERE d.name = $department_name DETACH DELETE d", department_name=department_name)

    return True

@app.route('/employees/<path:name>', methods=['DELETE'])
def delete_employee_by_name_route(name):
    name_without_spaces = name.replace(' ', '')

    with driver.session() as session:
        success = session.write_transaction(delete_employee_by_name, name_without_spaces)
        if success:
            return jsonify({"message": f"Pracownik o imieniu {name} został usunięty pomyślnie"})
        else:
            return jsonify({"error": f"Pracownik o imieniu {name} nie istnieje"}), 404



@app.route('/employees/<path:employee_name>/subordinates', methods=['GET'])
def get_subordinates(employee_name):
    with driver.session() as session:
        result = session.run(
            "MATCH (manager:Employee)-[:MANAGES]->(subordinate:Employee) "
            "WHERE REPLACE(manager.name, ' ', '') = $employee_name "
            "RETURN subordinate.name AS subordinate_name, subordinate.position AS subordinate_position, subordinate.salary AS subordinate_salary",
            employee_name=employee_name
        )

        subordinates = [{"name": record["subordinate_name"], "position": record["subordinate_position"], "salary": record["subordinate_salary"]} for record in result]

        return jsonify(subordinates)

# Endpoint do pobierania informacji o departamencie
@app.route('/department/<string:department_name>', methods=['GET'])
def get_department_info(department_name):
    with driver.session() as session:
        result = session.run(
            "MATCH (department:Department {name: $department_name}) "
            "OPTIONAL MATCH (employee:Employee)-[:WORKS_IN]->(department) "
            "WITH department, COLLECT(employee) AS employees "
            "RETURN department.name AS department_name, "
            "SIZE(employees) AS department_employee_count",
            department_name=department_name
        )

        department_info = result.single()
        if not department_info:
            return jsonify({"error": f"Nie znaleziono departamentu o nazwie {department_name}"}), 404

        manager_result = session.run(
            "MATCH (employee:Employee)-[:WORKS_IN]->(department:Department {name: $department_name}) "
            "WHERE employee.position = 'manager' "
            "RETURN COLLECT(employee.name) AS managers",
            department_name=department_name
        )

        managers = manager_result.single()["managers"]

        department_info = dict(department_info)
        department_info["managers"] = managers
        return jsonify(department_info)

def get_departments(tx, filter_criteria=None, sort_by=None):

    query = "MATCH (d:Department) RETURN d.name AS department_name, [(d)<-[:WORKS_IN]-() | 1] AS employees"
    if filter_criteria:
        query += f" WHERE {filter_criteria}"

    if sort_by:
        query += f" ORDER BY {sort_by}"

    result = tx.run(query)
    return [{"department_name": record["department_name"], "employee_count": len(record["employees"])} for record in result]

@app.route('/departments', methods=['GET'])
def get_departments_route():
    filter_criteria = request.args.get('filter')
    sort_by = request.args.get('sort')

    with driver.session() as session:
        departments = session.read_transaction(get_departments, filter_criteria, sort_by)
        return jsonify(departments)

@app.route('/departments/<string:department_name>/employees', methods=['GET'])
def get_department_employees(department_name):
    with driver.session() as session:
        result = session.run(
            "MATCH (e:Employee)-[:WORKS_IN]->(d:Department {name: $department_name}) "
            "RETURN e.name AS employee_name, e.position AS employee_position, e.salary AS employee_salary",
            department_name=department_name
        )

        employees = [{"name": record["employee_name"], "position": record["employee_position"], "salary": record["employee_salary"]} for record in result]

        return jsonify(employees)
    
if __name__ == "__main__":
    app.run()