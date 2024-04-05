# UML Diagrams 

## Diagrams 
The diagrams were made using [PlantUML](https://plantuml.com/) diagram creation.
The class diagram and the sequence diagram were used to setup diagrams that can display the overall process, structure or interaction between classes.

### Sequence Diagrams
The sequence diagrams are used to the sequence of a process. The diagram shows the order of functions being called as well as the classes that call the function. 
The diagrams contain information on: 
* a global example of howthe server handles callback commands to pass info the client. 
* the server receives a callback and sends the speech to the through each step all the way to the client.
* the server and client interact to set up a connection.

### Class Diagrams
The class diagram structure is used in two manners: an overview of the hierarchy between classes, and the interaction between classes with the focus of one class.
* The Unicorn NVDA diagram focusses on the hierarchy of the most relevant classes for the setup and interaction of the RDP connection, including the noteworthy variables and functions.
* The session and transport diagram use the structure of a class diagram to showcase the hierarchy, inheritance and interaction of the class it's focussed on. As the member variables that they have are largely the same e.g., the ```CallbackManager```, but the usage of the class and the relevant functions differ, it's desirable to have seperate interaction diagrams that show how they make use of the classes.
