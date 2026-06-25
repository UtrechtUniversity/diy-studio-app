<?php
header("Content-Type: application/json");

// Database connection
$servername = "localhost";
$username = "username";
$password = "password";
$dbname = "dbname";
$stats_table = "stats";
$studios_table = "studios";

$conn = new mysqli($servername, $username, $password, $dbname);

if ($conn->connect_error) {
    die(json_encode(["status" => "error", "message" => "Connection failed: " . $conn->connect_error]));
}

// Get JSON input
$data = json_decode(file_get_contents("php://input"), true);

if ($data) {
    // Check if studio exists, if not insert it
    $studio_name = $data['studio'];
    $stmt = $conn->prepare("SELECT id FROM $studios_table WHERE studio = ?");
    $stmt->bind_param("s", $studio_name);
    $stmt->execute();
    $stmt->store_result();
    
    if ($stmt->num_rows > 0) {
        $stmt->bind_result($studio_id);
        $stmt->fetch();
    } else {
        $stmt = $conn->prepare("INSERT INTO $studios_table (studio) VALUES (?)");
        $stmt->bind_param("s", $studio_name);
        if ($stmt->execute()) {
            $studio_id = $stmt->insert_id;
        } else {
            die(json_encode(["status" => "error", "message" => "Failed to insert studio"]));
        }
    }
    $stmt->close();

    // Insert data into main table
    $stmt = $conn->prepare("INSERT INTO $stats_table (studio_id, date, recs_total, recs_good, custom_file_names, avg_filesize, ppt_download_amnt, recs_ppt, recs_static, bg1, bg2, bg3, bg4, bg5, bg6, bg7, bg8, errors, logout) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)");
    $stmt->bind_param("isiiiiiiiidiiiiiiii", 
        $studio_id, $data['date'], $data['recs_total'], $data['recs_good'], 
        $data['custom_file_names'], $data['avg_filesize'], $data['ppt_download_amnt'], 
        $data['recs_ppt'], $data['recs_static'], $data['bg1'], $data['bg2'], $data['bg3'], 
        $data['bg4'], $data['bg5'], $data['bg6'], $data['bg7'], $data['bg8'], 
        $data['errors'], $data['logout']
    );

    if ($stmt->execute()) {
        echo json_encode(["status" => "success", "message" => "Data inserted successfully"]);
    } else {
        echo json_encode(["status" => "error", "message" => "Failed to insert data"]);
    }

    $stmt->close();
} else {
    echo json_encode(["status" => "error", "message" => "Invalid input"]);
}

$conn->close();
?>