function Invoke-TechTrackerPsql {
    param(
        [string]$Psql,
        [string]$HostName,
        [string]$Port,
        [string]$AdminUser,
        [string]$AdminPassword,
        [string]$Database = "postgres",
        [string]$Sql
    )
    $oldPassword = $env:PGPASSWORD
    try {
        $env:PGPASSWORD = $AdminPassword
        & $Psql -h $HostName -p $Port -U $AdminUser -d $Database -v ON_ERROR_STOP=1 -c $Sql
        if ($LASTEXITCODE -ne 0) {
            throw "psql завершился с кодом $LASTEXITCODE"
        }
    } finally {
        $env:PGPASSWORD = $oldPassword
    }
}

function Invoke-TechTrackerPsqlScalar {
    param(
        [string]$Psql,
        [string]$HostName,
        [string]$Port,
        [string]$AdminUser,
        [string]$AdminPassword,
        [string]$Database = "postgres",
        [string]$Sql
    )
    $oldPassword = $env:PGPASSWORD
    try {
        $env:PGPASSWORD = $AdminPassword
        $output = & $Psql -h $HostName -p $Port -U $AdminUser -d $Database -v ON_ERROR_STOP=1 -tAc $Sql
        if ($LASTEXITCODE -ne 0) {
            throw "psql завершился с кодом $LASTEXITCODE"
        }
        return ([string]($output | Select-Object -First 1)).Trim()
    } finally {
        $env:PGPASSWORD = $oldPassword
    }
}

function Initialize-TechTrackerDatabase {
    param([hashtable]$Config)

    Assert-TechTrackerSafeIdentifier -Value $Config.DbName -Name "DB_NAME"
    Assert-TechTrackerSafeIdentifier -Value $Config.DbUser -Name "DB_USER"

    $psql = Find-TechTrackerPsql
    if (-not $psql) {
        throw "psql не найден. Установите PostgreSQL или добавьте psql.exe в PATH."
    }

    $dbName = $Config.DbName
    $dbUser = $Config.DbUser
    $dbPassword = ([string]$Config.DbPassword).Replace("'", "''")
    $hostName = $Config.DbHost
    $port = $Config.DbPort
    $adminUser = $Config.PgAdminUser
    $adminPassword = $Config.PgAdminPassword

    Invoke-TechTrackerStep "Создание PostgreSQL пользователя $dbUser" {
        $sql = @"
DO `$do`$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '$dbUser') THEN
        CREATE ROLE "$dbUser" LOGIN PASSWORD '$dbPassword';
    ELSE
        ALTER ROLE "$dbUser" WITH LOGIN PASSWORD '$dbPassword';
    END IF;
END
`$do`$;
"@
        Invoke-TechTrackerPsql -Psql $psql -HostName $hostName -Port $port -AdminUser $adminUser -AdminPassword $adminPassword -Sql $sql
    }

    Invoke-TechTrackerStep "Создание PostgreSQL базы $dbName" {
        $existsSql = "SELECT 1 FROM pg_database WHERE datname = '$dbName';"
        $exists = Invoke-TechTrackerPsqlScalar -Psql $psql -HostName $hostName -Port $port -AdminUser $adminUser -AdminPassword $adminPassword -Sql $existsSql
        if ($exists -eq "1") {
            Write-TechTrackerLog "База $dbName уже существует" "OK"
            return
        }

        $sql = "CREATE DATABASE `"$dbName`" OWNER `"$dbUser`";"
        Invoke-TechTrackerPsql -Psql $psql -HostName $hostName -Port $port -AdminUser $adminUser -AdminPassword $adminPassword -Sql $sql
    }

    Invoke-TechTrackerStep "Выдача прав PostgreSQL" {
        $sql = "GRANT ALL PRIVILEGES ON DATABASE `"$dbName`" TO `"$dbUser`";"
        Invoke-TechTrackerPsql -Psql $psql -HostName $hostName -Port $port -AdminUser $adminUser -AdminPassword $adminPassword -Sql $sql
    }
}
