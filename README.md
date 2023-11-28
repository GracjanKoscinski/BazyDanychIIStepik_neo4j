# Employee Management API

This API is built using Neo4j and Flask framework in Python. It provides functionality for managing employees and departments within an organization.
It is hosted on Render at [https://bazydanychiineo4jflask.onrender.com/employees](https://bazydanychiineo4jflask.onrender.com/employees).

# Available Endpoints:

### 1. **GET - /employees**
   - Returns all employees with the option for filtering and sorting.

### 2. **POST - /employees**
   - Adds new employees and managers.

### 3. **PUT - /employees/:employee_name**
   - Allows editing employee details.

### 4. **DELETE - /employees/:employee_name**
   - Allows deleting employees. If their position is a manager, the entire department will be removed.

### 5. **GET - /employees/:employee_name/subordinates**
   - Displays subordinates of a specific manager.

### 6. **GET - /departments**
   - Shows names of all departments.

### 7. **GET - /department/:department_name**
   - Displays additional information about a department.

### 8. **GET - /departments/:department_name/employees**
   - Shows employees of a specific department.
