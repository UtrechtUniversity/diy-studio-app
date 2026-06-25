<?php
// This script will receive a log from the Python application
// when a user presses F10 and anytime an error message is displayed.
// The log will be send to the provided e-mail address.
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $logContent = isset($_POST['log']) ? $_POST['log'] : '';
    
    if (!empty($logContent)) {
        $to = 'your_email@example.com'; // Replace with your email address
        $subject = 'DIY Studio Log';
        $headers = "From: no-reply@yourwebsite.com\r\n";
        $headers .= "Content-Type: text/plain; charset=UTF-8\r\n";
        
        // Send the email
        if (mail($to, $subject, $logContent, $headers)) {
            echo 'Log sent successfully.';
        } else {
            http_response_code(500);
            echo 'Failed to send log.';
        }
    } else {
        http_response_code(400);
        echo 'No log content received.';
    }
} else {
    http_response_code(405);
    echo 'Method not allowed.';
}
?>