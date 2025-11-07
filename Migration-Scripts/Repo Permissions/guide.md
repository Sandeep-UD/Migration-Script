### User Mapping Guide

#### 1. Download User List
- Go to your Organization’s **People** tab.
- Download the user list as a CSV file.

#### 2. Prepare User Alignment Sheet
- Open the CSV in a spreadsheet application (Excel, Google Sheets, etc.).
- Identify and copy the columns:
  - `login`
  - `saml_name_id`
- Create a new sheet with columns: **login**, **saml_name_id**.
- Paste the copied values under the respective headers.

#### 3. Map to EMU Handle
- Add a new column: **emu_handle**.
- Map each user’s `login` and `saml_name_id` to their `emu_handle`.
- Your sheet should look like:

    ```csv
    login,saml_name_id,emu_handle
    MihirKulkarni11,mihir.kulkarni@ecanarys.com,mihir-kulkarni_ecanarys
    vaishnavn02,vaishnav.nugala@ecanarys.com,vaishnav-nugala_ecanarys
    ```

- Name the sheet as **user-align**.

#### 4. Create User Mapping Sheet
- Create a new sheet named **user-mapping**.
- Copy values from **fetch_repo_permissions.csv** into this sheet.

#### 5. Map EMU User
- Add a new column: **EMU User**.
- Use VLOOKUP to map `emu_handle` to each user:

    ```
    =VLOOKUP(C2, 'user-align'!A:C, 3, FALSE)
    ```

- The final **user-mapping** sheet should look like:

    ```csv
    Organization,Repository,User,User Permission,EMU User
    Demo-workshop-org,task-2,MihirKulkarni11,write,mihir-kulkarni_ecanarys
    Demo-workshop-org,action-example,vaishnavn02,admin,vaishnav-nugala_ecanarys
    ```