This snapshot configuration file type is used along with the **filesystem** connector. It allows you to take snaphots of entire files as resources to test.

# Supported IaC file types.
1. `json:` Crawl and process valid JSON files.
2. `yaml:` Crawl and process valid YAML files.
3. `arm:` Azure arm template.
4. `cloudformation:` AWS Cloud​Formation template.
5. `deploymentmanager:` Google cloud deploymentmanager.
6. `terraform:` Terraform files.
7. `kubernetesObjectFiles:` Kubernetes files.
8. `helmChart:` Kubernetes Helm Charts.
9. `ack:` AWS Controllers for Kubernetes.
10. `aso:` Azure Service Operator.
11. `kcc:` GCP Kubernetes Config Connector.

# Snapshot configuration file

To setup a **filesystem** snapshot configuration file, copy the following code to a file named `snapshot.json` in your container's folder.

> <NoteTitle>Notes: Naming conventions</NoteTitle>
>
> This file can be named anything you want but we suggest `snapshot.json`

    {
        "fileType": "snapshot",
        "snapshots": [
            {
                "source": "<name-of-connector>",
                "type": "filesystem",
                "testUser": "<user-to-use-on-connector>",
                "branchName": "<branch-to-use-on-connector>",
                "nodes": [
                    {
                        "snapshotId": "<snapshot-name>",
                        "type": "<file-type>",
                        "collection": "<collection-name>",
                        "paths": [
                            "<relative-paths-to-file>"
                        ]
                    }
                ]
            }
        ]
    }

Remember to substitute all values in this file that looks like a `<tag>` such as:

| tag | What to put there |
|-----|-------------------|
| name-of-connector | name of the **filesystem** connector configuration file |
| user-to-use-on-connector | Same username as defined in the **filesystem** connector configuration file |
| branch-to-use-on-connector | Same branch as defined in the **filesystem** connector configuration file. This attribute is only used when we are connecting to a **git** repository |
| snapshot-name | Name of the snapshot, you will use this in test files |
| file-type | type of the file, which should be one of the supported file type.|
| collection-name | Name of the **NoSQL** database collection used to store snapshots of this file |
| relative-paths-to-file | Path to the file to read, relative to the root of the repository that the connector checks out |

# Master Snapshot configuration file
We use master snapshot configuration file to read all the files in a directory with the **filesystem** connector. 
> <NoteTitle>Notes: Naming conventions</NoteTitle>
>
> This file can be named anything you want but we suggest `snapshot.json`

    {
        "fileType": "masterSnapshot",
        "snapshots": [
            {
                "source": "<name-of-connector>",
                "testUser": "<user-to-use-on-connector>",
                "nodes": [
                    {
                        "masterSnapshotId": "<master-snapshot-name>",
                        "type": "<file-type>",
                        "collection": "<collection-name>",
                        "paths": [
                            "<relative-paths-to-file>"
                        ],
                        "exclude" : {
                            "paths" : [
                                "<exclude-paths-to-file>"
                            ],
                            "regex" : [
                                "<regular-expression-to-exclude-file>"
                            ]
                        }
                    }
                ]
            }
        ]
    }

Remember to substitute all values in this file that looks like a `<tag>` such as:

| tag | What to put there |
|-----|-------------------|
| name-of-connector | name of the **filesystem** connector configuration file |
| user-to-use-on-connector | Same username as defined in the **filesystem** connector configuration file |
| branch-to-use-on-connector | Same branch as defined in the **filesystem** connector configuration file. This attribute is only used when we are connecting to a **git** repository |
| master-snapshot-name | Name of the snapshot, you will use this in test files |
| file-type | type of the file, which should be one of the supported file type.|
| collection-name | Name of the **NoSQL** database collection used to store snapshots of this file |
| relative-paths-to-file | Path to the file to read, relative to the root of the repository that the connector checks out |
| exclude-paths-to-file | Path to the file to exclude, relative to the root of the repository that the connector checks out |
| regular-expression-to-exclude-file | regular expression which matches with the filename or directory path to exclude  |