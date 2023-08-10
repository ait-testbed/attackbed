void setBuildStatus(String message, String state) {
    step([
        $class: "GitHubCommitStatusSetter",
        reposSource: [$class: "ManuallyEnteredRepositorySource", url: "https://github.com/ait-aecid/logdata-anomaly-miner"],
        contextSource: [$class: "ManuallyEnteredCommitContextSource", context: "ci/jenkins/build-status"],
        errorHandlers: [[$class: "ChangingBuildStatusErrorHandler", result: "UNSTABLE"]],
        statusResultSource: [ $class: "ConditionalStatusResultSource", results: [[$class: "AnyBuildResult", message: message, state: state]] ]
    ]);
}

def  docsimage = false

pipeline {
    agent any
    stages {
        stage("Build Documentation") {
        agent { 
                dockerfile { 
                             dir 'docs' 
                             args '-v $PWD:/docs'
                } 
        }
        	 when {
        	        expression {
        	                BRANCH_NAME == "main" || BRANCH_NAME == "development"
        	        }
        	}
        	steps {
                       sh "pwd"
                            sh "pwd"
            	            script {
        	                    docsimage = true
        	            }
                            sh "cd docs"
        	            sh "docker run --rm -v ${PWD}:/docs aecid/aminer-docs make html"
//        	            sh "scripts/deploydocs.sh ${env.BRANCH_NAME} ${env.BUILDDOCSDIR}/html /var/www/aeciddocs/logdata-anomaly-miner"
                }
        }
    }
    
    post {
        success {
            setBuildStatus("Build succeeded", "SUCCESS");
        }
        failure {
            setBuildStatus("Build failed", "FAILURE");
        }
    } 
}
