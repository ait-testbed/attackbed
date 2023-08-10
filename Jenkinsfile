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
                                     reuseNode true
                        } 
                }
        	when {
        	        expression {
        	                BRANCH_NAME == "main" || BRANCH_NAME == "development"
        	        }
        	}
        	steps {
            	        script {
        	                docsimage = true
        	        }
                        dir("docs") {
        	                sh "make html"
//        	                sh "scripts/deploydocs.sh ${env.BRANCH_NAME} ${env.BUILDDOCSDIR}/html /var/www/aeciddocs/logdata-anomaly-miner"
                        }
                }
        }
        stage("Deploy Docs") {
                steps {
                	sh "find"
                	sh "pwd"
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
