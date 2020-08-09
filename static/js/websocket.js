
$(document).ready(function()
{
    // ------------------------------ WEBSOCKET -----------------------------------------------//

    // Use a "/test" namespace.
    // An application can open a connection on multiple namespaces, and
    // Socket.IO will multiplex all those connections on a single
    // physical channel. If you don't care about multiple channels, you
    // can set the namespace to an empty string.
    namespace = '/rti';

    // Connect to the Socket.IO server.
    // The connection URL has the following format, relative to the current page:
    //     http[s]://<domain>:<port>[/<namespace>]
    var socket = io(namespace);

    // Event handler for new connections.
    // The callback function is invoked when a connection with the
    // server is established.
    socket.on('connect', function() {
        init_volt_plot(0, 0);
    });

    // Event handler for new connections.
    // The callback function is invoked when a connection with the
    // server is established.
    socket.on('disconnect', function() {

    });


    // Event handler for server sent data.
    // The callback function is invoked whenever the server emits data
    // to the client. The data is then displayed in the "Received"
    // section of the page.
    socket.on('status_report', function(msg, cb) {
        //$('#log').append('<br>' + $('<div/>').text('Received #' + msg.count + ': ' + msg.data).html());
        //if (cb)
        //    cb();
    });

    /**
     * Update the serial communication console to see the latest serial
     * communication
     */
    socket.on('serial_comm', function(msg, cb) {
        console.log("serial_comm");
        // Update the console
        $("textarea#txtSerialOutput").html(msg.data);
    });

    /**
     * Receiver the latest Ensemble information
     */
    socket.on('adcp_ens', function(msg, cb) {
        // Update the ensemble number
        $("#adcpEnsNumLabel").text(msg.adcp_ens_num);
        $("#adcpEnsNumStatusLabel").text(msg.adcp_ens_num);
    });

    /**
     * Create the plots.  This will get the initial date and time for the
     * plots.
     */
    socket.on('init_plots', function (msg) {
        // Function defined in volt_plot.js
        init_volt_plot( msg.x, msg.y );
    });

    /**
     * Update the volt plot with the latest data.
     */
    socket.on('update_volt_plot', function (msg) {
        // Function defined in volt_plot.js
        update_volt_plot( msg.x, msg.y );
    });

});