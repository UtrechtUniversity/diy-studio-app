<!DOCTYPE html>
<html>
<head>
    <title>DIY Studio Stats</title>
    <style>
		body {
				font-family: Arial
		}
        table {
            width: 30%;
            border-collapse: collapse;
        }
        th, td {
            border: 1px solid black;
            padding: 8px;
            text-align: left;
        }
        th {
            background-color: #f2f2f2;
        }
    </style>
</head>
<body>
    <h1>DIY Studio Stats</h1>
    <?php
    $servername = "localhost";
    $username = "username";
    $password = "password";
    $dbname = "dbname";

    $conn = new mysqli($servername, $username, $password, $dbname);
    if ($conn->connect_error) {
		echo "<p>Connection error!</p>";
        die("Connection failed: " . $conn->connect_error);
    }

    $totalRowsResult = $conn->query("SELECT COUNT(*) AS total_sessions FROM stats");
    $totalSessions = 0;

    if ($totalRowsResult && $row = $totalRowsResult->fetch_assoc()) {
        $totalSessions = $row['total_sessions'];
    }

    $sql = "SELECT st.studio AS studio_name, 
                   SUM(sd.recs_total) AS recs_total, SUM(sd.recs_good) AS recs_good,
                   SUM(sd.custom_file_names) AS custom_file_names, SUM(sd.avg_filesize) AS avg_filesize,
                   SUM(sd.ppt_download_amnt) AS ppt_download_amnt, SUM(sd.recs_ppt) AS recs_ppt,
                   SUM(sd.recs_static) AS recs_static, SUM(sd.bg1) AS bg1, SUM(sd.bg2) AS bg2,
                   SUM(sd.bg3) AS bg3, SUM(sd.bg4) AS bg4, SUM(sd.bg5) AS bg5, SUM(sd.bg6) AS bg6,
                   SUM(sd.bg7) AS bg7, SUM(sd.bg8) AS bg8, SUM(sd.errors) AS errors, SUM(sd.logout) AS logout
            FROM stats sd
            JOIN studios st ON sd.studio_id = st.id
            GROUP BY st.studio";

    $result = $conn->query($sql);
	
	if (!$result) {
        die("<p style='color:red;'>Query failed: " . $conn->error . "</p>");
    }
	
	// echo "<p>Number of rows returned: " . $result->num_rows . "</p>";

    if ($result->num_rows > 0) {
        while ($row = $result->fetch_assoc()) {
            echo "<h2>" . htmlspecialchars($row["studio_name"]) . "</h2>";
            echo "<table>";
            echo "<tr><th>Category</th><th>Total</th></tr>";
            echo "<tr><td>Sessions</td><td>$totalSessions</td></tr>";
            foreach ($row as $key => $value) {
                if ($key != "studio_name") {
                    echo "<tr><td>" . ucfirst(str_replace('_', ' ', htmlspecialchars($key))) . "</td><td>" . htmlspecialchars($value) . "</td></tr>";
                }
            }
            echo "</table>";
        }
    } else {
        echo "<p>No data available</p>";
    }

    $conn->close();
    ?>
</body>
</html>
