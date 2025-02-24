from flask import Flask, request, jsonify, render_template, send_file
import yaml
import os

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['CONVERTED_FOLDER'] = 'converted'


os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['CONVERTED_FOLDER'], exist_ok=True)

def clean_metadata(metadata):
    fields_to_remove = ["managedFields", "resourceVersion", "uid", "creationTimestamp", "generation"]
    for field in fields_to_remove:
        if field in metadata:
            del metadata[field]
    return metadata

def extract_strategy_params(strategy):
    rolling_update = strategy.get("rollingParams", {})
    max_unavailable = rolling_update.get("maxUnavailable")
    max_surge = rolling_update.get("maxSurge")
    
    strategy_data = {"type": "RollingUpdate"}
    if max_unavailable is not None:
        strategy_data.setdefault("rollingUpdate", {})["maxUnavailable"] = max_unavailable
    if max_surge is not None:
        strategy_data.setdefault("rollingUpdate", {})["maxSurge"] = max_surge
    
    return strategy_data

def process_containers(containers):
    processed_containers = []
    for container in containers:
        env = container.get("env", [])
        processed_env = []
        for env_var in env:
            if "value" in env_var or "valueFrom" in env_var:
                processed_env.append(env_var)
        container["env"] = processed_env
        processed_containers.append(container)
    return processed_containers

def convert_deploymentconfig_to_deployment(dc_yaml):
    try:
        dc_data = yaml.safe_load(dc_yaml)
        
        deployment_data = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": clean_metadata(dc_data.get("metadata", {})),
            "spec": {
                "replicas": dc_data["spec"].get("replicas"),
                "revisionHistoryLimit": dc_data["spec"].get("revisionHistoryLimit"),
                "selector": {
                    "matchLabels": dc_data["spec"]["selector"].get("matchLabels")
                },
                "strategy": extract_strategy_params(dc_data["spec"].get("strategy", {})),
                "template": {
                    "metadata": dc_data["spec"]["template"].get("metadata", {}),
                    "spec": {
                        "containers": process_containers(dc_data["spec"]["template"]["spec"].get("containers", []))
                    }
                }
            }
        }

        if deployment_data["spec"]["replicas"] is None:
            del deployment_data["spec"]["replicas"]
        if deployment_data["spec"]["revisionHistoryLimit"] is None:
            del deployment_data["spec"]["revisionHistoryLimit"]
        if not deployment_data["spec"]["selector"]["matchLabels"]:
            del deployment_data["spec"]["selector"]["matchLabels"]
        if not deployment_data["spec"]["strategy"]:
            del deployment_data["spec"]["strategy"]
        if not deployment_data["spec"]["template"]["spec"]["containers"]:
            del deployment_data["spec"]["template"]["spec"]["containers"]

        return yaml.dump(deployment_data, default_flow_style=False)
    except Exception as e:
        return f"Hata: {str(e)}"

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")

@app.route("/convert", methods=["POST"])
def convert():
    if 'file' not in request.files:
        return jsonify({"error": "Dosya yüklenmedi"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Dosya seçilmedi"}), 400
    

    if not file.filename.endswith(('.yaml', '.yml')):
        return jsonify({"error": "Geçersiz dosya türü"}), 400


    filename = os.path.splitext(file.filename)[0] + ".yaml"
    

    file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    file.save(file_path)
    

    with open(file_path, 'r') as f:
        dc_yaml = f.read()
    deployment_yaml = convert_deploymentconfig_to_deployment(dc_yaml)
    
    if "Hata:" in deployment_yaml:
        return jsonify({"error": deployment_yaml}), 400
    

    converted_file_path = os.path.join(app.config['CONVERTED_FOLDER'], filename)
    with open(converted_file_path, 'w') as f:
        f.write(deployment_yaml)
    
    return jsonify({"message": "Dönüştürme başarılı!", "download_url": f"/download/{filename}"})

@app.route("/download/<filename>", methods=["GET"])
def download(filename):
    converted_file_path = os.path.join(app.config['CONVERTED_FOLDER'], filename)
    if not os.path.exists(converted_file_path):
        return jsonify({"error": "Dosya bulunamadı"}), 404
    return send_file(converted_file_path, as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True)
