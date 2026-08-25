<?php
$target_base = 'https://quest.ms.mff.cuni.cz/wmt-humeval/';

$clean_uri = preg_replace('#^/wmt/#', '/', $_SERVER['REQUEST_URI']);
$target_url = $target_base . ltrim($clean_uri, '/');

$ch = curl_init($target_url);
$method = $_SERVER['REQUEST_METHOD'];
curl_setopt($ch, CURLOPT_CUSTOMREQUEST, $method);

$headers = [];
$strip_req_headers = ['host', 'accept-encoding', 'connection'];

foreach ($_SERVER as $k => $v) {
    if (strpos($k, 'HTTP_') === 0) {
        $name = str_replace('_', '-', substr($k, 5));
        if (in_array(strtolower($name), $strip_req_headers))
            continue;
        $headers[] = "$name: $v";
    } elseif ($k === 'CONTENT_TYPE') {
        $headers[] = "Content-Type: $v";
    }
}
curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);

if (in_array($method, ['POST', 'PUT', 'PATCH', 'DELETE'])) {
    $input = fopen('php://input', 'r');
    if ($input) {
        curl_setopt($ch, CURLOPT_UPLOAD, true);
        curl_setopt($ch, CURLOPT_INFILE, $input);
        
        $content_length = isset($_SERVER['HTTP_CONTENT_LENGTH']) ? $_SERVER['HTTP_CONTENT_LENGTH'] : 
                         (isset($_SERVER['CONTENT_LENGTH']) ? $_SERVER['CONTENT_LENGTH'] : null);
        if ($content_length !== null) {
            curl_setopt($ch, CURLOPT_INFILESIZE, (int)$content_length);
        }
        // Ensure the correct HTTP method is used instead of defaulting to PUT
        curl_setopt($ch, CURLOPT_CUSTOMREQUEST, $method);
    }
}

// Stream the response directly to stdout without buffering it
curl_setopt($ch, CURLOPT_RETURNTRANSFER, false);
curl_setopt($ch, CURLOPT_HEADER, false);
curl_setopt($ch, CURLOPT_FOLLOWLOCATION, false);
curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, true);
curl_setopt($ch, CURLOPT_SSL_VERIFYHOST, 2);

// Handle response headers via callback as they arrive
$strip_res_headers = ['transfer-encoding', 'connection', 'content-encoding'];
curl_setopt($ch, CURLOPT_HEADERFUNCTION, function($curl, $header) use ($strip_res_headers) {
    $len = strlen($header);
    $hdr = trim($header);
    
    // Extract HTTP status code and set it
    if (preg_match('#^HTTP/(1\.0|1\.1|2|3)\s+(\d{3})#i', $hdr, $matches)) {
        http_response_code((int)$matches[2]);
        return $len;
    }
    
    if (empty($hdr)) {
        return $len;
    }
    
    $parts = explode(':', $hdr, 2);
    if (count($parts) === 2) {
        $name = strtolower(trim($parts[0]));
        if (!in_array($name, $strip_res_headers)) {
            $replace = ($name !== 'set-cookie');
            header($hdr, $replace);
        }
    }
    return $len;
});

$response = curl_exec($ch);

if ($response === false) {
    // Only set bad gateway if we haven't started streaming headers/body yet
    if (!headers_sent()) {
        http_response_code(502);
    }
    die('Bad Gateway');
}

if (isset($input) && is_resource($input)) {
    fclose($input);
}
?>